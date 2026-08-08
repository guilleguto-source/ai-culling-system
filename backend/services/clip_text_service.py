import logging
from pathlib import Path
import numpy as np
import os

from services.app_paths import get_models_dir as _get_models_dir, get_resource as _get_resource

logger = logging.getLogger(__name__)

MODELS_DIR = _get_models_dir()
CLIP_TEXT_MODEL_PATH = MODELS_DIR / "clip_vit_b32_text.onnx"
# Tokenizador bundleado como recurso de sólo lectura (vocab/merges de CLIP, ~3.5 MB).
# En dev: backend/models/clip_tokenizer/ ; en packaged: resources/models/clip_tokenizer/
TOKENIZER_DIR = _get_resource("models/clip_tokenizer")

_session = None
_tokenizer = None
_session_failed = False


def is_available() -> bool:
    """True si el modelo ONNX de texto existe y puede cargarse."""
    return _get_session() is not None


def _get_session():
    global _session, _tokenizer, _session_failed
    if _session is not None and _tokenizer is not None:
        return _session
    if _session_failed:
        return None

    if not CLIP_TEXT_MODEL_PATH.exists():
        logger.warning(
            f"Modelo CLIP texto no encontrado en {CLIP_TEXT_MODEL_PATH}. "
            "La búsqueda semántica estará desactivada."
        )
        _session_failed = True
        return None

    if not TOKENIZER_DIR.exists():
        logger.warning(
            f"Tokenizador CLIP no encontrado en {TOKENIZER_DIR}. La búsqueda "
            "semántica estará desactivada (ver models/README.md para empaquetarlo)."
        )
        _session_failed = True
        return None

    try:
        # Offline forzado: el tokenizador vive en disco, nunca se descarga en
        # tiempo de uso. Así la feature no depende de internet ni de HuggingFace.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

        from transformers import CLIPTokenizer
        import onnxruntime as ort

        _tokenizer = CLIPTokenizer.from_pretrained(str(TOKENIZER_DIR), local_files_only=True)
        _session = ort.InferenceSession(str(CLIP_TEXT_MODEL_PATH), providers=["CPUExecutionProvider"])
        logger.info("Modelo de texto CLIP ViT-B/32 (ONNX) + tokenizador local cargados.")
        return _session
    except Exception as e:
        logger.error(f"No se pudo cargar el modelo CLIP de texto: {e}")
        _session_failed = True
        return None


def embed_text(query: str) -> np.ndarray | None:
    """
    Calcula el embedding L2-normalizado (float32, 512 dims) de una frase de texto.
    """
    session = _get_session()
    if session is None or not query.strip():
        return None
        
    try:
        # Tokenizar el texto
        inputs = _tokenizer(
            query, 
            padding="max_length", 
            max_length=77, 
            truncation=True, 
            return_tensors="np"
        )
        
        # Este export solo toma input_ids (sin attention_mask) y devuelve
        # text_embeds (batch, 512) como único output.
        onnx_inputs = {"input_ids": inputs["input_ids"].astype(np.int64)}
        out = session.run(None, onnx_inputs)
        vec = np.ravel(out[0]).astype(np.float32)
        
        # Normalizar L2 para similitud coseno mediante producto punto
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
        
    except Exception as e:
        logger.error(f"Error calculando embedding de texto para '{query}': {e}")
        return None
