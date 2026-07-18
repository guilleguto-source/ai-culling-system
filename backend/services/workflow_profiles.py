"""
workflow_profiles.py — Fase V: perfiles de workflow.

Un fotógrafo no trabaja igual una boda que un evento infantil o una sesión
corporativa: cambia la selectividad, el recorte, el preset y la exposición. Sin
perfiles, hay que re-configurar a mano en cada evento (y olvidarse de algo).

Un perfil es un paquete con nombre de las PREFERENCIAS que ya existen — no
inventa parámetros nuevos. Se guarda junto a los settings, en
%APPDATA%/ai_culling_system/profiles.json.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Claves de `prefs` que definen un perfil. Deliberadamente NO incluye
# ratings_mapping: el mapeo a estrellas/colores de Lightroom es del fotógrafo,
# no del tipo de evento, y cambiarlo por perfil sería una sorpresa desagradable.
CLAVES_PERFIL = (
    "selectivity_target", "auto_crop", "detect_duplicates", "detect_closed_eyes",
    "detect_blurry", "detect_highlights", "overwrite_xmp_ratings",
    "ensure_person_coverage", "pre_edit",
)


def _ruta() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "ai_culling_system"
    d.mkdir(parents=True, exist_ok=True)
    return d / "profiles.json"


def _leer() -> dict:
    p = _ruta()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"profiles.json ilegible: {e}")
        return {}


def _escribir(data: dict) -> bool:
    try:
        _ruta().write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"No se pudo guardar profiles.json: {e}")
        return False


def list_profiles() -> list[str]:
    return sorted(_leer().keys())


def save_profile(nombre: str, prefs: dict[str, Any]) -> dict:
    """Guarda las preferencias actuales bajo un nombre."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El perfil necesita un nombre")
    data = _leer()
    data[nombre] = {k: prefs[k] for k in CLAVES_PERFIL if k in prefs}
    _escribir(data)
    return {"guardado": nombre, "claves": len(data[nombre])}


def apply_profile(nombre: str, prefs: dict[str, Any]) -> dict[str, Any]:
    """
    Devuelve las prefs con el perfil aplicado encima. No pisa lo que el perfil
    no define, así que ajustes ajenos al workflow se conservan.
    """
    perfil = _leer().get(nombre)
    if perfil is None:
        raise KeyError(f"No existe el perfil '{nombre}'")
    return {**prefs, **perfil}


def delete_profile(nombre: str) -> bool:
    data = _leer()
    if nombre not in data:
        return False
    del data[nombre]
    return _escribir(data)
