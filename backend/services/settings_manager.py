"""
settings_manager.py — Gestión de la configuración persistente del sistema de culling.
Lee y escribe settings.json en %APPDATA%/ai_culling_system/ (Windows).
"""
import os
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Configuración por defecto del sistema, según las preferencias del fotógrafo
DEFAULT_SETTINGS: dict[str, Any] = {
    # Labels de color en español para coincidir con el conjunto de etiquetas
    # del Lightroom del usuario. selected=2★ (elegidas), highlighted=3★
    # (las top que no pueden faltar), Rojo = para borrar.
    # flag → banderín XMP (PickStatus): "pick" | "reject" | "none".
    # duplicates (Trash) va SIN color: no ensucia la vista de Lightroom.
    # Rojo = descarte real (se borra): pérdida total, o la peor de la ráfaga
    # (más ojos cerrados que la ganadora). Las duplicadas son fotos BUENAS que
    # solo perdieron su grupo → sin marcar, para no ensuciar Lightroom.
    "settings_version": 6,
    "ratings_mapping": {
        "selected": {"stars": 2, "color": "Verde", "flag": "pick"},
        "highlighted": {"stars": 3, "color": "Azul", "flag": "pick"},
        "blurry": {"stars": 0, "color": "Rojo", "flag": "reject"},
        "closed_eyes": {"stars": 0, "color": "", "flag": "none"},
        "duplicates": {"stars": 0, "color": "", "flag": "none"},
    },
    "selection_preferences": {
        "selectivity_target": "standard",   # "few" | "standard" | "more"
        "detect_duplicates": True,
        "detect_highlights": True,
        "detect_blurry": True,
        "blurry_sensitivity": "moderate",   # "lenient" | "moderate" | "strict"
        "detect_closed_eyes": True,
        "overwrite_xmp_ratings": False,
        # Defaults calibrados contra el historial real del fotógrafo (2026-07-27):
        # su edición es mínima e intencional, y las correcciones automáticas
        # geométricas/de WB no predicen su criterio. Ver
        # docs/.../2026-07-27-pre-revelado-calibracion.md. Todo queda disponible
        # como opt-in; solo cambia el default a "no estorbar".
        "auto_crop": "off",                 # "off" | "minimo" | "medio" | "agresivo"
        "auto_straighten": False,           # rotación por horizonte: erraba 4.8° vs 1.3° real
        "pre_edit": {
            "enabled": True,
            "preset_path": "",              # .xmp de LR activo ("" = sin preset)
            "exposure_bias": 0.0,           # -0.5 .. +0.5 (era 0.3: peor que no tocar)
            "exposure_deadband": 0.15,      # no emitir correcciones de exposición menores a esto (EV)
            "auto_wb": False,               # WB por piel: opera en espacio incremental que el usuario (RAW) no usa
            "recent_presets": [],           # [{name, path}] MRU máx 5
        },
    },
    "last_import_directory": "",
}

# Umbrales de varianza Laplaciana por nivel de sensibilidad de borrosidad
BLUR_THRESHOLDS = {
    "lenient": 30.0,
    "moderate": 80.0,
    "strict": 150.0,
}

# DBSCAN epsilon (distancia de hash Hamming) por nivel de selectividad
SELECTIVITY_EPSILON = {
    "few": 18,       # Grupos más grandes, cull más agresivo (selecciona menos fotos)
    "standard": 12,
    "more": 8,       # Grupos más pequeños, cull más indulgente (selecciona más fotos)
}


def _get_settings_path() -> Path:
    """Retorna la ruta del archivo settings.json según el OS."""
    app_data = os.environ.get("APPDATA") or str(Path.home())
    settings_dir = Path(app_data) / "ai_culling_system"
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir / "settings.json"


def load_settings() -> dict[str, Any]:
    """
    Carga la configuración desde settings.json.
    Si el archivo no existe o está corrupto, retorna los valores por defecto.
    """
    path = _get_settings_path()
    if not path.exists():
        logger.info("settings.json no encontrado. Usando configuración por defecto.")
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Migrate duplicates color from Yellow or Red to Purple if existing
        if "ratings_mapping" in data and "duplicates" in data["ratings_mapping"]:
            if data["ratings_mapping"]["duplicates"].get("color") in ("Yellow", "Red"):
                data["ratings_mapping"]["duplicates"]["color"] = "Purple"
                save_settings(data) # Persist the migrated settings
        # Migración v2: selected pasa a 2★ (highlighted queda como las 3★
        # imprescindibles) y colores al español del set de LR del usuario.
        if data.get("settings_version", 1) < 2 and "ratings_mapping" in data:
            _COLOR_ES = {"Green": "Verde", "Blue": "Azul", "Red": "Rojo",
                         "Purple": "Morado", "Yellow": "Amarillo"}
            rm = data["ratings_mapping"]
            for entry in rm.values():
                entry["color"] = _COLOR_ES.get(entry.get("color"), entry.get("color"))
            if rm.get("selected", {}).get("stars") == 3:
                rm["selected"]["stars"] = 2
            data["settings_version"] = 2
            save_settings(data)
        # Migración v3: banderines XMP configurables y Trash (duplicates) sin color
        if data.get("settings_version", 1) < 3 and "ratings_mapping" in data:
            rm = data["ratings_mapping"]
            _DEFAULT_FLAGS = {"selected": "pick", "highlighted": "pick",
                              "blurry": "reject", "closed_eyes": "reject",
                              "duplicates": "none"}
            for label, entry in rm.items():
                entry.setdefault("flag", _DEFAULT_FLAGS.get(label, "none"))
            if "duplicates" in rm:
                rm["duplicates"]["color"] = ""
            data["settings_version"] = 3
            save_settings(data)
        # Migración v4: el set de LR del usuario usa masculino (Rojo/Morado);
        # los nombres femeninos de la v2 NO pintan en Lightroom.
        if data.get("settings_version", 1) < 4 and "ratings_mapping" in data:
            _FIX_GENERO = {"Roja": "Rojo", "Morada": "Morado", "Amarilla": "Amarillo"}
            for entry in data["ratings_mapping"].values():
                entry["color"] = _FIX_GENERO.get(entry.get("color"), entry.get("color"))
            data["settings_version"] = 4
            save_settings(data)
        # Migración v5: corrige el mapeo inducido por el nombre "Trash" que la
        # UI le daba a `duplicates` (fotos buenas que perdieron su ráfaga). El
        # rojo/rechazo pasa a los descartes reales y las duplicadas se limpian.
        if data.get("settings_version", 1) < 5 and "ratings_mapping" in data:
            rm = data["ratings_mapping"]
            dup = rm.get("duplicates", {})
            if dup.get("color") == "Rojo" or dup.get("flag") == "reject":
                dup["color"] = ""
                dup["flag"] = "none"
                for label in ("blurry", "closed_eyes"):
                    rm.setdefault(label, {"stars": 0})
                    rm[label]["color"] = "Rojo"
                    rm[label]["flag"] = "reject"
            data["settings_version"] = 5
            save_settings(data)
        # Migración v6: closed_eyes ya no se marca como Rojo/reject.
        # Eran fotos buenas que perdieron por parpadeo comparativo, marcarlas
        # en rojo las confunde con basura real (blurry/exposure).
        if data.get("settings_version", 1) < 6 and "ratings_mapping" in data:
            rm = data["ratings_mapping"]
            ce = rm.get("closed_eyes", {})
            if ce.get("color") == "Rojo" or ce.get("flag") == "reject":
                ce["color"] = ""
                ce["flag"] = "none"
            data["settings_version"] = 6
            save_settings(data)
        # Merge con defaults para garantizar que nuevas claves estén presentes
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        return merged
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error leyendo settings.json: {e}. Usando defaults.")
        return DEFAULT_SETTINGS.copy()


# El set de etiquetas de Lightroom del usuario está en español MASCULINO.
# Un nombre en femenino o inglés NO pinta el color: se normaliza siempre al
# guardar, para que un frontend viejo o un JSON editado a mano no lo rompan.
COLOR_CANONICO = {
    "roja": "Rojo", "rojo": "Rojo", "red": "Rojo",
    "amarilla": "Amarillo", "amarillo": "Amarillo", "yellow": "Amarillo",
    "verde": "Verde", "green": "Verde",
    "azul": "Azul", "blue": "Azul",
    "morada": "Morado", "morado": "Morado", "purple": "Morado",
}


def normalize_colors(settings: dict[str, Any]) -> dict[str, Any]:
    """Canoniza los nombres de color del ratings_mapping (in-place)."""
    for entry in settings.get("ratings_mapping", {}).values():
        color = (entry.get("color") or "").strip()
        if color:
            entry["color"] = COLOR_CANONICO.get(color.lower(), color)
    return settings


def save_settings(settings: dict[str, Any]) -> bool:
    """Guarda la configuración en settings.json."""
    path = _get_settings_path()
    try:
        normalize_colors(settings)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuración guardada en {path}")
        return True
    except OSError as e:
        logger.error(f"Error guardando settings.json: {e}")
        return False


def get_blur_threshold(settings: dict[str, Any]) -> float:
    """Retorna el umbral de varianza Laplaciana según la sensibilidad configurada."""
    sensitivity = settings.get("selection_preferences", {}).get(
        "blurry_sensitivity", "moderate"
    )
    return BLUR_THRESHOLDS.get(sensitivity, BLUR_THRESHOLDS["moderate"])


def get_dbscan_epsilon(settings: dict[str, Any]) -> int:
    """Retorna el epsilon de DBSCAN según el nivel de selectividad configurado."""
    target = settings.get("selection_preferences", {}).get(
        "selectivity_target", "standard"
    )
    return SELECTIVITY_EPSILON.get(target, SELECTIVITY_EPSILON["standard"])


def _deep_merge(base: dict, override: dict) -> dict:
    """Fusiona dos dicts de forma recursiva, override tiene prioridad."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
