"""
app_paths.py — Resolutor centralizado de rutas para dev y producción (PyInstaller).

En modo desarrollo los datos viven junto al código fuente.
En modo producción (app empaquetada) los datos del usuario van a %APPDATA%/GutoFlow/
y los recursos de sólo lectura (LUTs, modelos bundleados) quedan en resources/.

USO:
    from services.app_paths import get_models_dir, get_user_data_dir, get_resource

    CLIP_MODEL  = get_models_dir() / "clip_vit_b32_visual.onnx"
    SETTINGS    = get_user_data_dir() / "settings.json"
    LUT_DIR     = get_resource("luts")   # bundleado en el instalador
"""
import os
import sys
import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Detección de entorno
# ─────────────────────────────────────────────────────────────────────────────

def _is_packaged() -> bool:
    """True cuando corremos dentro de un ejecutable PyInstaller."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _project_root() -> Path:
    """Raíz del proyecto en modo desarrollo."""
    # este archivo vive en backend/services/app_paths.py
    return Path(__file__).parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Rutas públicas
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_user_data_dir() -> Path:
    """
    Directorio de datos de usuario (escribible):
    - Dev:        <project_root>/backend/models/
    - Packaged:   %APPDATA%/GutoFlow/   (Windows)
                  ~/Library/Application Support/GutoFlow/  (macOS — futuro)
                  ~/.config/GutoFlow/  (Linux — futuro)
    """
    if _is_packaged():
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        d = base / "GutoFlow"
    else:
        d = _project_root() / "backend" / "models"

    d.mkdir(parents=True, exist_ok=True)
    return d


@lru_cache(maxsize=1)
def get_models_dir() -> Path:
    """
    Directorio donde residen los modelos ONNX / .task descargables.
    Siempre es un subdirectorio de `get_user_data_dir()` para que el usuario
    no pierda los modelos al actualizar la app.
    """
    d = get_user_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


@lru_cache(maxsize=None)
def get_resource(relative: str) -> Path:
    """
    Localiza un recurso de sólo lectura bundleado con la app:
    - Dev:        <project_root>/backend/<relative>
    - Packaged:   <resources_path>/<relative>   (junto al .exe)

    Ejemplo: get_resource("models/luts") → .../backend/models/luts/
    """
    if _is_packaged():
        # PyInstaller extrae recursos junto al ejecutable en _MEIPASS
        # o en el directorio del exe si se usó --onedir
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / relative
        if candidate.exists():
            return candidate
        # fallback al temp de _MEIPASS (--onefile)
        return Path(sys._MEIPASS) / relative
    else:
        return _project_root() / "backend" / relative


# ─────────────────────────────────────────────────────────────────────────────
# Subdirectorios de datos de usuario
# ─────────────────────────────────────────────────────────────────────────────

def get_exports_dir() -> Path:
    d = get_user_data_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_undo_dir() -> Path:
    d = get_user_data_dir() / "undo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_emb_cache_dir() -> Path:
    d = get_user_data_dir() / "emb_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_analysis_dir() -> Path:
    d = get_user_data_dir() / "analysis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_presets_dir() -> Path:
    d = get_user_data_dir() / "presets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_path() -> Path:
    return get_user_data_dir() / "settings.json"


def get_develop_recipes_path() -> Path:
    return get_user_data_dir() / "develop_recipes.json"


# ─────────────────────────────────────────────────────────────────────────────
# Diagnóstico
# ─────────────────────────────────────────────────────────────────────────────

def log_paths():
    """Imprime todas las rutas resueltas al iniciar la app (útil para debug)."""
    logger.info(f"[app_paths] packaged={_is_packaged()}")
    logger.info(f"[app_paths] user_data_dir={get_user_data_dir()}")
    logger.info(f"[app_paths] models_dir={get_models_dir()}")
    logger.info(f"[app_paths] luts_resource={get_resource('models/luts')}")
