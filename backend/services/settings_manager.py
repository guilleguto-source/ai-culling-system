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
    "ratings_mapping": {
        "selected": {"stars": 3, "color": "Green"},
        "highlighted": {"stars": 3, "color": "Blue"},
        "blurry": {"stars": 0, "color": "Red"},
        "closed_eyes": {"stars": 0, "color": "Purple"},
        "duplicates": {"stars": 0, "color": "Purple"},
    },
    "selection_preferences": {
        "selectivity_target": "standard",   # "few" | "standard" | "more"
        "detect_duplicates": True,
        "detect_highlights": True,
        "detect_blurry": True,
        "blurry_sensitivity": "moderate",   # "lenient" | "moderate" | "strict"
        "detect_closed_eyes": True,
        "overwrite_xmp_ratings": False,
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
