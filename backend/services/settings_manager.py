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
    # (las top que no pueden faltar), Roja = para borrar.
    # flag → banderín XMP (PickStatus): "pick" | "reject" | "none".
    # duplicates (Trash) va SIN color: no ensucia la vista de Lightroom.
    "settings_version": 3,
    "ratings_mapping": {
        "selected": {"stars": 2, "color": "Verde", "flag": "pick"},
        "highlighted": {"stars": 3, "color": "Azul", "flag": "pick"},
        "blurry": {"stars": 0, "color": "Roja", "flag": "reject"},
        "closed_eyes": {"stars": 0, "color": "Morada", "flag": "reject"},
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
        "auto_crop": "minimo",              # "off" | "minimo" | "medio" | "agresivo"
        "pre_edit": {
            "enabled": True,
            "preset_path": "",              # .xmp de LR activo ("" = sin preset)
            "exposure_bias": 0.3,           # -0.5 .. +0.5
            "recent_presets": [],           # [{name, path}] MRU máx 5
        },
    },
    "last_import_directory": "",
    "culling_mode": "assisted",             # "assisted" | "automatic"
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
            _COLOR_ES = {"Green": "Verde", "Blue": "Azul", "Red": "Roja",
                         "Purple": "Morada", "Yellow": "Amarilla"}
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
        # Merge con defaults para garantizar que nuevas claves estén presentes
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        return merged
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error leyendo settings.json: {e}. Usando defaults.")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict[str, Any]) -> bool:
    """Guarda la configuración en settings.json."""
    path = _get_settings_path()
    try:
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
