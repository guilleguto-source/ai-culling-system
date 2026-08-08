"""
setup.py — Router de configuración inicial y descarga de modelos.

Endpoints:
  GET  /setup/models          — catálogo y estado de todos los modelos
  POST /setup/download        — inicia descarga de los modelos indicados
  GET  /setup/download/stream — SSE con progreso en tiempo real
  GET  /setup/required_ready  — True si todos los modelos requeridos están presentes
"""
import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.model_downloader import (
    get_models_status,
    start_download,
    is_downloading,
    get_all_states,
    MODEL_CATALOG,
)
from services.app_paths import get_models_dir

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/setup", tags=["setup"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class DownloadRequest(BaseModel):
    model_ids: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    """Devuelve el catálogo de modelos con estado de descarga y presencia en disco."""
    return {"models": get_models_status()}


@router.get("/required_ready")
def required_ready():
    """True si todos los modelos marcados como required están presentes."""
    statuses = get_models_status()
    missing = [m["id"] for m in statuses if m["required"] and not m["present"]]
    return {"ready": len(missing) == 0, "missing": missing}


@router.post("/download")
def start_model_download(req: DownloadRequest):
    """Inicia la descarga de los modelos indicados en background."""
    if is_downloading():
        return {"started": False, "message": "Ya hay una descarga en curso"}
    ok = start_download(req.model_ids)
    return {"started": ok, "message": "Descarga iniciada" if ok else "Sin modelos válidos en la lista"}


@router.get("/download/stream")
async def download_progress_stream():
    """
    Server-Sent Events con el progreso de descarga.
    El cliente se suscribe y recibe actualizaciones cada 500 ms hasta que
    todas las descargas solicitadas terminan.
    """
    async def event_generator():
        while True:
            states = get_all_states()
            data = json.dumps(states)
            yield f"data: {data}\n\n"

            # Cerrar el stream si nada está descargando
            if not is_downloading():
                # Enviar un último frame con el estado final
                states = get_all_states()
                data = json.dumps(states)
                yield f"data: {data}\n\n"
                yield "event: done\ndata: {}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
