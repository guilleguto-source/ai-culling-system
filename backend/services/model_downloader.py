"""
model_downloader.py — Gestor de descarga de modelos pesados para primera ejecución.

Define el catálogo de modelos requeridos con sus URLs, tamaños y destinos.
Expone progreso vía callback para que el endpoint SSE lo retransmita al frontend.

Diseño:
  - Descarga atómica: escribe a .tmp y hace rename sólo si el SHA256 coincide.
  - Reanudación: si el .tmp existe y el servidor soporta Range, continúa.
  - Degradación: los modelos ONNX son opcionales — la app funciona sin ellos.
"""
import hashlib
import logging
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from services.app_paths import get_models_dir

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo de modelos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    id: str
    display_name: str
    filename: str          # dentro de get_models_dir()
    url: str
    size_mb: float         # tamaño aproximado para la UI
    sha256: Optional[str] = None   # None = sin verificación
    required: bool = False         # True = app no funciona sin él
    description: str = ""


MODEL_CATALOG: list[ModelSpec] = [
    ModelSpec(
        id="face_landmarker",
        display_name="Detector Facial (MediaPipe)",
        filename="face_landmarker.task",
        url="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
        size_mb=6.0,
        required=True,
        description="Detecta ojos, sonrisa y micro-expresiones. Requerido para el culling.",
    ),
    ModelSpec(
        id="clip_visual",
        display_name="CLIP Visual (búsqueda semántica)",
        filename="clip_vit_b32_visual.onnx",
        url="https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx",
        size_mb=300.0,
        required=False,
        description="Permite buscar fotos por descripción: 'niños riendo', 'primer plano'. Opcional.",
    ),
    ModelSpec(
        id="clip_text",
        display_name="CLIP Texto (búsqueda semántica)",
        filename="clip_vit_b32_text.onnx",
        url="https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/text_model.onnx",
        size_mb=250.0,
        required=False,
        description="Complemento al CLIP Visual para procesar la consulta de texto. Opcional.",
    ),
    ModelSpec(
        id="arcface",
        display_name="Reconocimiento de Personas (ArcFace)",
        filename="arcface_r50.onnx",
        url="https://huggingface.co/guto-ai/arcface-r50/resolve/main/arcface_r50.onnx",
        size_mb=150.0,
        required=False,
        description="Garantiza al menos una foto por persona en el evento. Opcional.",
    ),
    ModelSpec(
        id="yolov8_person",
        display_name="Detector de Personas (YOLOv8)",
        filename="person_yolov8n.onnx",
        url="https://huggingface.co/guto-ai/yolov8n-person/resolve/main/person_yolov8n.onnx",
        size_mb=6.5,
        required=False,
        description="Detecta personas de espaldas para el auto-encuadre. Opcional.",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Estado de descarga (hilo único, acceso thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DownloadState:
    model_id: str
    status: str = "idle"        # idle | downloading | verifying | done | error
    progress: float = 0.0       # 0–100
    error: Optional[str] = None
    bytes_done: int = 0
    bytes_total: int = 0


_lock = threading.Lock()
_states: dict[str, DownloadState] = {m.id: DownloadState(m.id) for m in MODEL_CATALOG}
_active_thread: Optional[threading.Thread] = None


def get_all_states() -> list[dict]:
    with _lock:
        return [
            {
                "id": s.model_id,
                "status": s.status,
                "progress": round(s.progress, 1),
                "error": s.error,
                "bytes_done": s.bytes_done,
                "bytes_total": s.bytes_total,
            }
            for s in _states.values()
        ]


def _update_state(model_id: str, **kwargs):
    with _lock:
        if model_id not in _states:
            _states[model_id] = DownloadState(model_id)
        s = _states[model_id]
        for k, v in kwargs.items():
            setattr(s, k, v)


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo público
# ─────────────────────────────────────────────────────────────────────────────

def get_models_status() -> list[dict]:
    """
    Estado de todos los modelos: presencia en disco + progreso de descarga.
    """
    models_dir = get_models_dir()
    result = []
    with _lock:
        for spec in MODEL_CATALOG:
            path = models_dir / spec.filename
            present = path.exists() and path.stat().st_size > 1024
            dl = _states[spec.id]
            result.append({
                "id": spec.id,
                "display_name": spec.display_name,
                "filename": spec.filename,
                "size_mb": spec.size_mb,
                "required": spec.required,
                "description": spec.description,
                "present": present,
                "download_status": dl.status,
                "download_progress": round(dl.progress, 1),
                "download_error": dl.error,
            })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_model(spec: ModelSpec):
    models_dir = get_models_dir()
    dest = models_dir / spec.filename
    tmp = models_dir / (spec.filename + ".tmp")

    if dest.exists() and dest.stat().st_size > 1024:
        _update_state(spec.id, status="done", progress=100.0)
        logger.info(f"[downloader] {spec.id} ya existe, omitiendo.")
        return

    _update_state(spec.id, status="downloading", progress=0.0, error=None)
    logger.info(f"[downloader] Descargando {spec.display_name} desde {spec.url}")

    try:
        # Soporte de reanudación
        headers = {}
        existing_bytes = tmp.stat().st_size if tmp.exists() else 0
        if existing_bytes > 0:
            headers["Range"] = f"bytes={existing_bytes}-"

        req = urllib.request.Request(spec.url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_length = int(resp.headers.get("Content-Length", 0))
            total = content_length + existing_bytes
            _update_state(spec.id, bytes_total=total)

            mode = "ab" if existing_bytes > 0 else "wb"
            done = existing_bytes
            with open(tmp, mode) as f:
                while True:
                    chunk = resp.read(1 << 16)   # 64 KB
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    progress = (done / total * 100) if total > 0 else 0
                    _update_state(spec.id, bytes_done=done, progress=progress)

        # Verificación opcional de hash
        if spec.sha256:
            _update_state(spec.id, status="verifying")
            computed = _sha256(tmp)
            if computed != spec.sha256:
                tmp.unlink(missing_ok=True)
                _update_state(spec.id, status="error",
                               error=f"SHA256 inválido: esperado {spec.sha256[:8]}…, obtenido {computed[:8]}…")
                return

        tmp.rename(dest)
        _update_state(spec.id, status="done", progress=100.0)
        logger.info(f"[downloader] {spec.id} descargado correctamente → {dest}")

    except Exception as e:
        logger.error(f"[downloader] Error descargando {spec.id}: {e}")
        _update_state(spec.id, status="error", error=str(e))


def start_download(model_ids: list[str]) -> bool:
    """
    Inicia la descarga de los modelos indicados en un hilo de fondo.
    Retorna False si ya hay una descarga activa.
    """
    global _active_thread
    with _lock:
        if _active_thread and _active_thread.is_alive():
            return False

    specs = [s for s in MODEL_CATALOG if s.id in model_ids]
    if not specs:
        return False

    def _run():
        for spec in specs:
            _download_model(spec)

    _active_thread = threading.Thread(target=_run, daemon=True, name="model-downloader")
    _active_thread.start()
    return True


def is_downloading() -> bool:
    return bool(_active_thread and _active_thread.is_alive())
