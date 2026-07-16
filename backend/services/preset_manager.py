"""
preset_manager.py — Carga y gestión de presets .xmp de Lightroom.
El preset del usuario aporta el "look" (curva, HSL, color grading, nitidez,
máscaras IA...). Se excluye lo que el sistema calcula por su cuenta
(exposición, WB, crop, AutoTone) y la metadata de catálogo del preset.
"""
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from services.settings_manager import load_settings, save_settings

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "models" / "presets"
MAX_RECENT = 5

NS_CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

# Campos crs que NO se fusionan en las fotos (ver spec 2026-07-15-pre-edicion):
# metadata de catálogo, y todo lo que el sistema calcula por su cuenta.
_BLACKLIST_EXACT = {
    # Metadata del preset
    "PresetType", "UUID", "Cluster", "Name", "ShortName", "SortName",
    "Group", "Description", "CameraModelRestriction", "Copyright",
    "ContactInfo", "CompatibleVersion", "Version", "CompressedSettings",
    "HasSettings", "AllowFilters",
    # Lo calculamos nosotros
    "AutoTone", "WhiteBalance", "IncrementalTemperature", "IncrementalTint",
    "Exposure2012", "Temperature", "Tint",
}
# Nota: "AutoTone" va por lista exacta — "AutoLateralCA" (corrección de lente)
# sí es parte del look y se conserva.
_BLACKLIST_PREFIX = ("Supports", "ShowIn", "Table_", "Crop")
_BLACKLIST_ELEMENTS = {
    "Name", "ShortName", "SortName", "Group", "Description", "FilterList",
}


@dataclass
class PresetData:
    name: str
    path: str
    settings: dict[str, str] = field(default_factory=dict)   # atributos crs a fusionar
    elements: list = field(default_factory=list, repr=False)  # subárboles XML (curvas, máscaras)
    wb_bias: tuple[float, float] = (0.0, 0.0)  # (temp, tint) del preset → sesgo


def _is_blacklisted(local_name: str) -> bool:
    if local_name in _BLACKLIST_EXACT:
        return True
    return any(local_name.startswith(p) for p in _BLACKLIST_PREFIX)


def _parse_float(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value.replace("+", ""))
    except ValueError:
        return 0.0


def load_preset(path: str) -> PresetData | None:
    """
    Parsea un preset .xmp de Lightroom (PV moderno). Retorna None si no es
    un preset válido — la pre-edición continúa sin preset.
    """
    p = Path(path)
    try:
        root = etree.parse(str(p)).getroot()
    except Exception as e:
        logger.warning(f"Preset ilegible {p.name}: {e}")
        return None

    desc = root.find(f".//{{{NS_RDF}}}Description")
    if desc is None:
        logger.warning(f"Preset sin rdf:Description: {p.name}")
        return None

    # Nombre legible (crs:Name/rdf:Alt/rdf:li) o el del archivo
    name = p.stem
    name_el = desc.find(f"{{{NS_CRS}}}Name/{{{NS_RDF}}}Alt/{{{NS_RDF}}}li")
    if name_el is not None and name_el.text:
        name = name_el.text.strip()

    settings: dict[str, str] = {}
    wb_temp = wb_tint = 0.0
    for attr, value in desc.attrib.items():
        if not attr.startswith(f"{{{NS_CRS}}}"):
            continue
        local = attr.split("}", 1)[1]
        if local == "IncrementalTemperature":
            wb_temp = _parse_float(value)
            continue
        if local == "IncrementalTint":
            wb_tint = _parse_float(value)
            continue
        if _is_blacklisted(local):
            continue
        settings[local] = value

    elements = []
    for child in desc:
        local = etree.QName(child).localname
        if local in _BLACKLIST_ELEMENTS or _is_blacklisted(local):
            continue
        elements.append(child)

    if not settings and not elements:
        logger.warning(f"Preset sin ajustes fusionables: {p.name}")
        return None

    logger.info(
        f"Preset '{name}': {len(settings)} ajustes, {len(elements)} bloques, "
        f"sesgo WB ({wb_temp:+.0f}, {wb_tint:+.0f})"
    )
    return PresetData(name=name, path=str(p), settings=settings,
                      elements=elements, wb_bias=(wb_temp, wb_tint))


def register_recent(path: str) -> dict:
    """
    Copia el preset a models/presets/ y lo pone primero en los recientes
    (MRU, máx 5). Devuelve el bloque pre_edit actualizado de settings.
    """
    src = Path(path)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PRESETS_DIR / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    settings = load_settings()
    pre = settings["selection_preferences"].setdefault("pre_edit", {})
    recent = [r for r in pre.get("recent_presets", []) if r.get("path") != str(dest)]
    recent.insert(0, {"name": src.stem, "path": str(dest)})
    pre["recent_presets"] = recent[:MAX_RECENT]
    pre["preset_path"] = str(dest)
    save_settings(settings)
    return pre
