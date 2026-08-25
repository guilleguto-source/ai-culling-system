"""
siglip_service.py — Visual embeddings con SigLIP (google/siglip-base-patch16-224).
Produce vectores de 768 dimensiones L2-normalizados para evaluación estética
y entrenamiento del Taste Model. Reemplaza a CLIP ViT-B/32 con un salto
sustancial en representación de detalle, color, composición e iluminación.
"""
import os
import ssl
import hashlib
import logging
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

# SSL Bypass para entorno de desarrollo Windows si es necesario
os.environ["HF_HUB_DISABLE_SSL_VERIFICATION"] = "1"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["PYTHONHTTPSVERIFY"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    import httpx
    _orig_client_init = httpx.Client.__init__
    def _patched_client_init(self, *args, **kwargs):
        kwargs['verify'] = False
        _orig_client_init(self, *args, **kwargs)
    httpx.Client.__init__ = _patched_client_init
except Exception:
    pass

from services.app_paths import get_emb_cache_dir

logger = logging.getLogger(__name__)

MODEL_ID = "google/siglip-base-patch16-224"
MODEL_VERSION = "siglip-base-p16-224"
EMBEDDING_DIM = 768
CACHE_DIR = get_emb_cache_dir()

_processor = None
_model = None
_load_failed = False


def _get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _load_model():
    global _processor, _model, _load_failed
    if _model is not None and _processor is not None:
        return _processor, _model
    if _load_failed:
        return None, None

    try:
        import torch
        from transformers import SiglipImageProcessor, SiglipVisionModel

        device = _get_device()
        logger.info(f"Cargando SigLIP Vision Model ({MODEL_ID}) en dispositivo: {device}...")

        _processor = SiglipImageProcessor.from_pretrained(MODEL_ID)
        _model = SiglipVisionModel.from_pretrained(MODEL_ID).to(device)
        _model.eval()

        logger.info("Modelo SigLIP cargado correctamente.")
        return _processor, _model
    except Exception as e:
        logger.error(f"Error cargando modelo SigLIP ({MODEL_ID}): {e}")
        _load_failed = True
        return None, None


def is_available() -> bool:
    """Retorna True si el modelo SigLIP está disponible o puede cargarse."""
    proc, mod = _load_model()
    return mod is not None


def embed(img_rgb: np.ndarray | None) -> np.ndarray | None:
    """
    Calcula el embedding SigLIP L2-normalizado (768 dims) de una imagen RGB.
    """
    if img_rgb is None or img_rgb.size == 0:
        return None

    processor, model = _load_model()
    if model is None or processor is None:
        return None

    try:
        import torch
        device = next(model.parameters()).device
        pil_img = Image.fromarray(img_rgb)
        inputs = processor(images=pil_img, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            features = outputs.pooler_output
            features = features / features.norm(p=2, dim=-1, keepdim=True)

        vec = features.squeeze(0).cpu().numpy().astype(np.float32)
        return vec
    except Exception as e:
        logger.error(f"Error generando embedding SigLIP: {e}")
        return None


def embed_batch(images_rgb: list[np.ndarray | None], batch_size: int = 32) -> list[np.ndarray | None]:
    """
    Calcula embeddings SigLIP para un lote de imágenes RGB en inferencia GPU/CPU vectorizada.
    """
    processor, model = _load_model()
    if model is None or processor is None or not images_rgb:
        return [None] * len(images_rgb)

    results: list[np.ndarray | None] = [None] * len(images_rgb)
    valid_items = [(idx, img) for idx, img in enumerate(images_rgb) if img is not None and img.size > 0]
    if not valid_items:
        return results

    import torch
    device = next(model.parameters()).device

    for i in range(0, len(valid_items), batch_size):
        chunk = valid_items[i:i + batch_size]
        chunk_indices = [item[0] for item in chunk]
        pil_images = [Image.fromarray(item[1]) for item in chunk]

        try:
            inputs = processor(images=pil_images, return_tensors="pt").to(device)
            with torch.no_grad():
                outputs = model(**inputs)
                features = outputs.pooler_output
                features = features / features.norm(p=2, dim=-1, keepdim=True)
                vecs = features.cpu().numpy().astype(np.float32)

            for idx, vec in zip(chunk_indices, vecs):
                results[idx] = vec
        except Exception as e:
            logger.error(f"Error procesando batch SigLIP: {e}")

    return results


# --- Cache Disk Storage ---

def _cache_file(path: str, mtime: float) -> Path:
    key = hashlib.sha1(f"siglip|{path}|{mtime}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"siglip_{key}.npy"


def load_cached_embedding(path: str, mtime: float) -> np.ndarray | None:
    cf = _cache_file(path, mtime)
    if not cf.exists():
        return None
    try:
        vec = np.load(cf)
        if vec.shape == (EMBEDDING_DIM,):
            return vec
    except Exception:
        pass
    return None


def save_cached_embedding(path: str, mtime: float, vec: np.ndarray) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cf = _cache_file(path, mtime)
        np.save(cf, vec)
    except Exception as e:
        logger.warning(f"No se pudo guardar caché SigLIP: {e}")


def embed_path(path: str, img_rgb: np.ndarray | None = None) -> np.ndarray | None:
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
            logger.warning(f"No se pudo guardar caché SigLIP: {e}")
    return vec
