"""
core/job_manager.py — Gestor de estado thread-safe para los trabajos de culling y caché en memoria.
Protege el acceso concurrente entre el hilo del pipeline de procesamiento y las peticiones REST de la UI.
"""
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class JobManager:
    """
    Administrador centralizado y thread-safe del estado del culling y thumbnails en memoria.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {
            "job_id": None,
            "status": "idle",        # idle | running | completed | error
            "progress": 0.0,
            "phase_text": "",
            "total": 0,
            "processed": 0,
            "results": [],
            "stats": {},
            "error": None,
            "mode": "cull_edit",
        }
        self._thumbnail_cache: dict[str, bytes] = {}
        self._thumbnail_duel_cache: dict[str, bytes] = {}

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._state["status"] == "running"

    def reset(self):
        """Reinicia el estado del JobManager al estado inicial idle."""
        with self._lock:
            self._state = {
                "job_id": None,
                "status": "idle",
                "progress": 0.0,
                "phase_text": "",
                "total": 0,
                "processed": 0,
                "results": [],
                "stats": {},
                "error": None,
                "mode": "cull_edit",
            }
            self._thumbnail_cache.clear()
            self._thumbnail_duel_cache.clear()

    def start_job(self, job_id: str, mode: str = "cull_edit") -> bool:
        """
        Inicia un nuevo trabajo si no hay uno en ejecución.
        Retorna True si se inició, False si ya había un trabajo corriendo.
        """
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._state = {
                "job_id": job_id,
                "status": "running",
                "progress": 0.0,
                "phase_text": "Iniciando culling...",
                "total": 0,
                "processed": 0,
                "results": [],
                "stats": {},
                "error": None,
                "mode": mode,
            }
            self._thumbnail_cache.clear()
            self._thumbnail_duel_cache.clear()
            return True

    def update_progress(
        self,
        processed: int | None = None,
        total: int | None = None,
        progress: float | None = None,
        phase_text: str | None = None,
    ):
        """Actualiza de forma atómica el progreso y fase del culling."""
        with self._lock:
            if processed is not None:
                self._state["processed"] = processed
            if total is not None:
                self._state["total"] = total
            if progress is not None:
                self._state["progress"] = round(progress, 1)
            if phase_text is not None:
                self._state["phase_text"] = phase_text

    def set_phase(self, phase_text: str):
        """Actualiza el texto descriptivo de la fase actual."""
        with self._lock:
            self._state["phase_text"] = phase_text

    def set_stat(self, key: str, value: Any):
        """Registra una métrica en el diccionario de stats."""
        with self._lock:
            self._state["stats"][key] = value

    def set_results(self, results: list[dict[str, Any]], stats: dict[str, Any] | None = None):
        """Marca el trabajo como completado y asigna los resultados finales."""
        with self._lock:
            self._state["results"] = results
            if stats is not None:
                self._state["stats"].update(stats)
            self._state["status"] = "completed"
            self._state["progress"] = 100.0
            self._state["phase_text"] = "Completado"

    def set_error(self, error_message: str):
        """Marca el trabajo con error."""
        with self._lock:
            self._state["status"] = "error"
            self._state["error"] = error_message
            self._state["phase_text"] = f"Error: {error_message}"

    def get_status(self) -> dict[str, Any]:
        """Retorna una copia superficial y consistente del estado actual."""
        with self._lock:
            return {
                "job_id": self._state["job_id"],
                "status": self._state["status"],
                "progress": self._state["progress"],
                "phase_text": self._state.get("phase_text", ""),
                "total": self._state["total"],
                "processed": self._state["processed"],
                "stats": dict(self._state["stats"]),
                "error": self._state["error"],
                "mode": self._state.get("mode", "cull_edit"),
            }

    def get_results(self) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Retorna (status, results, stats) bajo lock."""
        with self._lock:
            return (
                self._state["status"],
                list(self._state["results"]),
                dict(self._state["stats"]),
            )

    # --- Cache de miniaturas en RAM ---

    def set_thumbnail(self, path: str, data: bytes, size: str = "ui"):
        with self._lock:
            if size == "duel":
                self._thumbnail_duel_cache[path] = data
            else:
                self._thumbnail_cache[path] = data

    def get_thumbnail(self, path: str, size: str = "ui") -> bytes | None:
        with self._lock:
            if size == "duel":
                return self._thumbnail_duel_cache.get(path)
            return self._thumbnail_cache.get(path)

    def clear_thumbnails(self):
        with self._lock:
            self._thumbnail_cache.clear()
            self._thumbnail_duel_cache.clear()

    # --- Soporte tipo Diccionario para compatibilidad hacia atrás ---

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._state[key]

    def __setitem__(self, key: str, value: Any):
        with self._lock:
            self._state[key] = value

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._state

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.get(key, default)


# Instancia Singleton compartida
job_manager = JobManager()
