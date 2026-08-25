"""
main.py — Punto de entrada del backend FastAPI para el sistema de Culling IA.
Orquestador modularizado que monta los routers REST consumidos por el proceso principal de Electron.
"""
import logging
import numpy as np

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import system, culling, bursts, export, media, advanced, setup

# Re-exportaciones de funciones para compatibilidad con tests existentes
from routers.culling import _run_culling_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Culling Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    from services.app_paths import log_paths
    log_paths()
    from services.thumbnail_store import auto_cleanup_cache
    try:
        auto_cleanup_cache(30)
        logger.info("Caché de miniaturas de más de 30 días limpiada de forma automática.")
    except Exception as e:
        logger.error(f"Error en auto-limpieza de caché: {e}")


# --- Montaje de Routers ---
app.include_router(system.router)
app.include_router(culling.router)
app.include_router(bursts.router)
app.include_router(export.router)
app.include_router(media.router)
app.include_router(advanced.router)
app.include_router(setup.router)


# Delegación dinámica de atributos para compatibilidad con tests (evita desincronización por reasignación)
def __getattr__(name: str):
    if name == "_job_state":
        return culling._job_state
    if name == "_thumbnail_cache":
        return media._thumbnail_cache
    if name == "_thumbnail_duel_cache":
        return media._thumbnail_duel_cache
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
