"""
embedding_service.py — Embeddings visuales con CLIP ViT-B/32 (ONNX, local).
Convierte cada foto en un vector de 512 dims que captura contenido completo
(gesto, expresión, composición, ambiente). Base del taste model por embeddings.

Degradación: si el modelo ONNX no está en backend/models/, is_available() es
False y el pipeline sigue funcionando solo con heurísticas (sin crash).
"""
import hashlib
import logging
from pathlib import Path

import cv2
import numpy as np

from services.app_paths import get_models_dir as _get_models_dir, get_emb_cache_dir as _get_emb_cache_dir

logger = logging.getLogger(__name__)

MODELS_DIR = _get_models_dir()
CLIP_MODEL_PATH = MODELS_DIR / "clip_vit_b32_visual.onnx"
CACHE_DIR = _get_emb_cache_dir()

MODEL_VERSION = "clip-vit-b32"
EMBEDDING_DIM = 512

# Preprocesado estándar de CLIP
_CLIP_SIZE = 224
_CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

# Sesión ONNX perezosa (se carga en el primer uso)
_session = None
_session_failed = False


def _get_onnx_providers() -> list[str]:
    """Retorna los mejores proveedores ONNX disponibles en orden de preferencia."""
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        preferred = ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
        selected = [p for p in preferred if p in available]
        return selected if selected else ["CPUExecutionProvider"]
    except Exception:
        return ["CPUExecutionProvider"]


def is_available() -> bool:
    """True si el modelo ONNX existe y puede cargarse."""
    return _get_session() is not None


def _get_session():
    global _session, _session_failed
    if _session is not None:
        return _session
    if _session_failed or not CLIP_MODEL_PATH.exists():
        if not CLIP_MODEL_PATH.exists() and not _session_failed:
            logger.warning(
                f"Modelo CLIP no encontrado en {CLIP_MODEL_PATH}. "
                "El ranking usará solo heurísticas (ver models/README.md para descargarlo)."
            )
            _session_failed = True
        return None
    try:
        import onnxruntime as ort
        providers = _get_onnx_providers()
        _session = ort.InferenceSession(str(CLIP_MODEL_PATH), providers=providers)
        logger.info(f"Modelo de embeddings CLIP ViT-B/32 cargado con proveedores: {providers}")
        return _session
    except Exception as e:
        logger.error(f"No se pudo cargar el modelo CLIP: {e}")
        _session_failed = True
        return None


def _preprocess(img_rgb: np.ndarray) -> np.ndarray:
    """Preprocesado CLIP: lado corto a 224 (bicúbico) + center crop + normalización."""
    h, w = img_rgb.shape[:2]
    scale = _CLIP_SIZE / min(h, w)
    nh, nw = round(h * scale), round(w * scale)
    img = cv2.resize(img_rgb, (nw, nh), interpolation=cv2.INTER_CUBIC)

    top = (nh - _CLIP_SIZE) // 2
    left = (nw - _CLIP_SIZE) // 2
    img = img[top:top + _CLIP_SIZE, left:left + _CLIP_SIZE]

    img = img.astype(np.float32) / 255.0
    img = (img - _CLIP_MEAN) / _CLIP_STD
    return img.transpose(2, 0, 1)[np.newaxis, ...]  # NCHW


def embed(img_rgb: np.ndarray) -> np.ndarray | None:
    """
    Calcula el embedding L2-normalizado (float32, 512 dims) de una imagen RGB.
    Retorna None si el modelo no está disponible o la imagen es inválida.
    """
    session = _get_session()
    if session is None or img_rgb is None or img_rgb.size == 0:
        return None
    try:
        x = _preprocess(img_rgb)
        in_name = session.get_inputs()[0].name
        out = session.run(None, {in_name: x})[0]
        vec = np.ravel(out).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    except Exception as e:
        logger.error(f"Error calculando embedding: {e}")
        return None


def embed_batch(images_rgb: list[np.ndarray | None], batch_size: int = 16) -> list[np.ndarray | None]:
    """
    Calcula embeddings L2-normalizados para un lote de imágenes RGB en inferencia vectorizada.
    """
    session = _get_session()
    if session is None or not images_rgb:
        return [None] * len(images_rgb)

    results: list[np.ndarray | None] = [None] * len(images_rgb)
    valid_items = [(idx, img) for idx, img in enumerate(images_rgb) if img is not None and img.size > 0]
    if not valid_items:
        return results

    in_name = session.get_inputs()[0].name
    for i in range(0, len(valid_items), batch_size):
        chunk = valid_items[i:i + batch_size]
        indices = [item[0] for item in chunk]
        tensors = []
        for _, img in chunk:
            try:
                tensors.append(_preprocess(img))
            except Exception as e:
                logger.error(f"Error preprocesando imagen para batch: {e}")
                tensors.append(None)

        batch_valid = [(idx, t) for idx, t in zip(indices, tensors) if t is not None]
        if not batch_valid:
            continue

        stacked = np.concatenate([t for _, t in batch_valid], axis=0)  # Shape (B, 3, 224, 224)
        try:
            outs = session.run(None, {in_name: stacked})[0]  # Shape (B, 512)
            for (out_idx, _), out_vec in zip(batch_valid, outs):
                vec = np.ravel(out_vec).astype(np.float32)
                norm = np.linalg.norm(vec)
                results[out_idx] = vec / norm if norm > 0 else vec
        except Exception as e:
            logger.error(f"Error en inferencia batch CLIP: {e}")

    return results


# --- Caché en disco keyed por (path, mtime) ---

def _cache_file(path: str, mtime: float) -> Path:
    key = hashlib.sha1(f"{path}|{mtime}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.npy"


def load_cached_embedding(path: str, mtime: float) -> np.ndarray | None:
    """
    Devuelve el embedding YA cacheado en disco (o None si no está / está
    corrupto). No decodifica la imagen ni toca el archivo original.
    """
    cf = _cache_file(path, mtime)
    if not cf.exists():
        return None
    try:
        vec = np.load(cf)
        if vec.shape == (EMBEDDING_DIM,):
            return vec
    except Exception:
        pass  # caché corrupto
    return None


def embed_path(path: str, img_rgb: np.ndarray | None = None) -> np.ndarray | None:
    """
    Embedding de una foto con caché en disco.
    """
    try:
        mtime = Path(path).stat().st_mtime
    except OSError:
        return embed(img_rgb) if img_rgb is not None else None

    cached = load_cached_embedding(path, mtime)
    if cached is not None:
        return cached

    if img_rgb is None:
        return None
    vec = embed(img_rgb)
    if vec is not None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            np.save(_cache_file(path, mtime), vec)
        except Exception as e:
            logger.warning(f"No se pudo guardar caché de embedding: {e}")
    return vec


def embed_paths_batch(items: list[tuple[str, np.ndarray | None]], batch_size: int = 16) -> list[np.ndarray | None]:
    """
    Embedding por lotes con caché en disco.
    items: lista de tuplas (path, img_rgb)
    """
    if not items:
        return []

    results: list[np.ndarray | None] = [None] * len(items)
    to_compute_indices = []
    to_compute_images = []
    mtimes = []

    for idx, (path, img_rgb) in enumerate(items):
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            mtime = None

        if mtime is not None:
            cached = load_cached_embedding(path, mtime)
            if cached is not None:
                results[idx] = cached
                continue

        if img_rgb is not None:
            to_compute_indices.append(idx)
            to_compute_images.append(img_rgb)
            mtimes.append(mtime)

    if to_compute_images:
        computed = embed_batch(to_compute_images, batch_size=batch_size)
        for res_idx, vec, mtime in zip(to_compute_indices, computed, mtimes):
            results[res_idx] = vec
            if vec is not None and mtime is not None:
                try:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    np.save(_cache_file(items[res_idx][0], mtime), vec)
                except Exception as e:
                    logger.warning(f"No se pudo guardar caché de embedding: {e}")

    return results
