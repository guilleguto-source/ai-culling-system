"""
embedding_service.py — Fachada de Embeddings Visuales (Ahora potenciada por SigLIP 768d).
Mantiene compatibilidad de importación para todos los servicios del backend.
"""
from pathlib import Path
import logging
import numpy as np
from services import siglip_service

logger = logging.getLogger(__name__)

MODEL_VERSION = siglip_service.MODEL_VERSION
EMBEDDING_DIM = siglip_service.EMBEDDING_DIM


def is_available() -> bool:
    return siglip_service.is_available()


def unload_model() -> None:
    """Descarga el modelo de embeddings visuales para liberar RAM/VRAM."""
    siglip_service.unload_model()


def embed(img_rgb: np.ndarray | None) -> np.ndarray | None:
    return siglip_service.embed(img_rgb)


def embed_batch(images_rgb: list[np.ndarray | None], batch_size: int = 32) -> list[np.ndarray | None]:
    return siglip_service.embed_batch(images_rgb, batch_size=batch_size)


def load_cached_embedding(path: str, mtime: float) -> np.ndarray | None:
    return siglip_service.load_cached_embedding(path, mtime)


def embed_path(path: str, img_rgb: np.ndarray | None = None) -> np.ndarray | None:
    return siglip_service.embed_path(path, img_rgb)


def embed_paths_batch(items: list[tuple[str, np.ndarray | None]], batch_size: int = 32) -> list[np.ndarray | None]:
    if not items:
        return []
    results: list[np.ndarray | None] = [None] * len(items)
    to_compute_indices = []
    to_compute_images = []

    for idx, (path, img_rgb) in enumerate(items):
        try:
            mtime = Path(path).stat().st_mtime
        except Exception:
            mtime = 0.0

        cached = load_cached_embedding(path, mtime)
        if cached is not None:
            results[idx] = cached
        elif img_rgb is not None:
            to_compute_indices.append(idx)
            to_compute_images.append(img_rgb)

    if to_compute_images:
        computed = embed_batch(to_compute_images, batch_size=batch_size)
        for res_idx, vec in zip(to_compute_indices, computed):
            results[res_idx] = vec
            if vec is not None:
                path, _ = items[res_idx]
                try:
                    mtime = Path(path).stat().st_mtime
                    siglip_service.save_cached_embedding(path, mtime, vec)
                except Exception:
                    pass

    return results
