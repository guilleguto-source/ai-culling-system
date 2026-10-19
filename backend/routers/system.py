"""
routers/system.py — Endpoints de diagnóstico, configuración, perfiles y ciclo de vida del sistema.
"""
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.settings_manager import load_settings, save_settings
from utils.hardware import get_hardware_info

logger = logging.getLogger(__name__)
router = APIRouter(tags=["System"])


def _code_stamp() -> float:
    """mtime más reciente del código del backend (main.py + routers/*.py + services/*.py)."""
    base = Path(__file__).parent.parent
    stamps = [os.path.getmtime(base / "main.py")]
    stamps += [os.path.getmtime(p) for p in (base / "routers").glob("*.py")]
    stamps += [os.path.getmtime(p) for p in (base / "services").glob("*.py")]
    return max(stamps)


# Se fija al ARRANCAR para detectar si el proceso en memoria quedó desactualizado
_LOADED_CODE_STAMP = _code_stamp()


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class SettingsUpdateRequest(BaseModel):
    ratings_mapping: dict | None = None
    selection_preferences: dict | None = None


class ProfileRequest(BaseModel):
    nombre: str


# --- Endpoints ---

@router.get("/health")
def health_check():
    try:
        stale = _code_stamp() > _LOADED_CODE_STAMP
    except OSError:
        stale = False
    return {"status": "ok", "version": "2.1.0", "stale_code": stale}


@router.get("/hardware")
def hardware_info():
    """Retorna información del hardware detectado (GPU/CPU) para mostrar en la UI."""
    return get_hardware_info()


@router.get("/settings")
def get_settings():
    return load_settings()


@router.post("/settings")
def update_settings(data: SettingsUpdateRequest):
    current = load_settings()
    if data.ratings_mapping is not None:
        current["ratings_mapping"].update(data.ratings_mapping)
    if data.selection_preferences is not None:
        current["selection_preferences"].update(data.selection_preferences)
    ok = save_settings(current)
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando la configuración")
    return {"success": True, "settings": current}


@router.get("/profiles")
def profiles_list():
    """Fase V: perfiles de workflow (bodas, infantil, corporativo…)."""
    from services.workflow_profiles import list_profiles
    return {"perfiles": list_profiles()}


@router.post("/profiles/save")
def profiles_save(data: ProfileRequest):
    """Guarda las preferencias actuales como un perfil con nombre."""
    from services.workflow_profiles import save_profile
    settings = load_settings()
    try:
        return save_profile(data.nombre, settings.get("preferences", {}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/profiles/apply")
def profiles_apply(data: ProfileRequest):
    """Aplica un perfil sobre las preferencias actuales y las persiste."""
    from services.workflow_profiles import apply_profile
    from services.settings_manager import save_settings
    settings = load_settings()
    try:
        settings["preferences"] = apply_profile(data.nombre, settings.get("preferences", {}))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    save_settings(settings)
    return {"aplicado": data.nombre, "settings": settings}


@router.post("/profiles/delete")
def profiles_delete(data: ProfileRequest):
    from services.workflow_profiles import delete_profile
    if not delete_profile(data.nombre):
        raise HTTPException(status_code=404, detail="No existe ese perfil")
    return {"eliminado": data.nombre}


@router.post("/shutdown")
def shutdown(background_tasks: BackgroundTasks):
    """Detiene el servidor backend de forma limpia."""
    def _do_shutdown():
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)
    background_tasks.add_task(_do_shutdown)
    return {"success": True}
