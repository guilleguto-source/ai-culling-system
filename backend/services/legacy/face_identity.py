"""
face_identity.py — Fase L: identidad de las personas (ArcFace).

Da un embedding de IDENTIDAD por rostro (distinto del CLIP de apariencia).
Agrupa por persona dentro de un evento por similitud coseno. Habilita
garantizar "al menos una buena foto de cada persona" y, a futuro, el mejor
ángulo de alguien.

Degradación como CLIP: si el modelo ONNX no está en models/, is_available()
es False y la función se desactiva sin romper el pipeline. El modelo
(arcface_r50.onnx, ~90-170 MB) se descarga aparte (ver models/README.md).
"""
import logging
from pathlib import Path
from typing import Any

import numpy as np

from services.app_paths import get_models_dir as _get_models_dir

logger = logging.getLogger(__name__)

MODEL_PATH = _get_models_dir() / "arcface_r50.onnx"
INPUT_SIZE = 112          # ArcFace estándar
IDENTITY_THRESHOLD = 0.38  # distancia coseno máx. para "misma persona" (calibrable)

# Plantilla estándar de ArcFace (5 puntos sobre 112x112): ojo, ojo, nariz,
# comisura, comisura — el mismo orden que entrega YuNet. Alinear a esta
# plantilla (rotación+escala+traslación) es lo que le da precisión al modelo.
import numpy as _np
_ARCFACE_DST = _np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=_np.float32)

_session = None
_failed = False


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
    return _get_session() is not None


def _get_session():
    global _session, _failed
    if _session is not None:
        return _session
    if _failed or not MODEL_PATH.exists():
        if not MODEL_PATH.exists() and not _failed:
            logger.warning(
                f"ArcFace no encontrado en {MODEL_PATH}. El reconocimiento de "
                "personas queda desactivado (ver models/README.md)."
            )
            _failed = True
        return None
    try:
        import onnxruntime as ort
        providers = _get_onnx_providers()
        _session = ort.InferenceSession(str(MODEL_PATH), providers=providers)
        logger.info(f"Modelo ArcFace cargado con proveedores: {providers}")
        return _session
    except Exception as e:
        logger.error(f"No se pudo cargar ArcFace: {e}")
        _failed = True
        return None


def _align(img_rgb: np.ndarray, landmarks) -> np.ndarray | None:
    """Alinea el rostro a 112x112 con la plantilla ArcFace, vía transformación
    de similitud (rotación+escala+traslación) desde los 5 puntos de YuNet."""
    import cv2
    kps = np.asarray(landmarks, dtype=np.float32)
    if kps.shape != (5, 2):
        return None
    M, _ = cv2.estimateAffinePartial2D(kps, _ARCFACE_DST, method=cv2.LMEDS)
    if M is None:
        return None
    return cv2.warpAffine(img_rgb, M, (INPUT_SIZE, INPUT_SIZE), borderValue=0.0)


def _crop_resize(img_rgb: np.ndarray, bbox: list[int]) -> np.ndarray | None:
    """Fallback sin landmarks: recorte por caja reescalado a 112x112."""
    import cv2
    h, w = img_rgb.shape[:2]
    x, y, fw, fh = bbox
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w, x + fw), min(h, y + fh)
    crop = img_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_CUBIC)


def embed_face(img_rgb: np.ndarray, bbox: list[int],
               landmarks=None) -> np.ndarray | None:
    """
    Embedding de identidad (512-d, L2-normalizado) del rostro.
    Con `landmarks` (los 5 puntos de YuNet) alinea a la plantilla ArcFace —
    fuerte salto de precisión. Sin ellos, cae al recorte por caja.
    None si el modelo no está o el recorte es inválido.
    """
    session = _get_session()
    if session is None or img_rgb is None or img_rgb.size == 0:
        return None

    chip = _align(img_rgb, landmarks) if landmarks is not None else None
    if chip is None:
        chip = _crop_resize(img_rgb, bbox)
    if chip is None:
        return None

    try:
        x_in = ((chip.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[np.newaxis, ...]
        out = session.run(None, {session.get_inputs()[0].name: x_in})[0]
        vec = np.ravel(out).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
    except Exception as e:
        logger.debug(f"ArcFace falló en un recorte: {e}")
        return None


def embed_faces_batch(
    faces_data: list[tuple[np.ndarray, list[int], Any]],
    batch_size: int = 16,
) -> list[np.ndarray | None]:
    """
    Embedding de identidad por lotes vectorizados para múltiples rostros.
    faces_data: lista de tuplas (img_rgb, bbox, landmarks).
    """
    session = _get_session()
    if session is None or not faces_data:
        return [None] * len(faces_data)

    results: list[np.ndarray | None] = [None] * len(faces_data)
    valid_items = []

    for idx, (img_rgb, bbox, landmarks) in enumerate(faces_data):
        if img_rgb is None or img_rgb.size == 0:
            continue
        chip = _align(img_rgb, landmarks) if landmarks is not None else None
        if chip is None and bbox:
            chip = _crop_resize(img_rgb, bbox)
        if chip is not None:
            tensor = ((chip.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[np.newaxis, ...]
            valid_items.append((idx, tensor))

    if not valid_items:
        return results

    in_name = session.get_inputs()[0].name
    for i in range(0, len(valid_items), batch_size):
        chunk = valid_items[i:i + batch_size]
        indices = [item[0] for item in chunk]
        stacked = np.concatenate([item[1] for item in chunk], axis=0)  # Shape (B, 3, 112, 112)
        try:
            outs = session.run(None, {in_name: stacked})[0]  # Shape (B, 512)
            for out_idx, out_vec in zip(indices, outs):
                vec = np.ravel(out_vec).astype(np.float32)
                norm = np.linalg.norm(vec)
                results[out_idx] = vec / norm if norm > 0 else vec
        except Exception as e:
            logger.debug(f"ArcFace batch run falló: {e}")

    return results


def group_identities(embeddings: list[np.ndarray],
                     threshold: float = IDENTITY_THRESHOLD) -> list[int]:
    """
    Agrupa embeddings de rostro por identidad (greedy por coseno). Devuelve una
    etiqueta de identidad por embedding (mismo índice de entrada). Lógica pura:
    el corazón testeable de la fase. `None` en la entrada → identidad -1.
    """
    ids: list[int] = []
    centroides: list[np.ndarray] = []
    for emb in embeddings:
        if emb is None:
            ids.append(-1)
            continue
        v = np.asarray(emb, dtype=np.float32)
        mejor, mejor_d = -1, threshold
        for k, c in enumerate(centroides):
            d = 1.0 - float(np.dot(v, c))   # distancia coseno (vectores normalizados)
            if d < mejor_d:
                mejor, mejor_d = k, d
        if mejor >= 0:
            ids.append(mejor)
        else:
            ids.append(len(centroides))
            centroides.append(v)
    return ids


def group_event_identities(embs_by_photo: dict,
                           threshold: float = IDENTITY_THRESHOLD) -> dict:
    """
    Agrupa TODOS los rostros de un evento por identidad y mapea de vuelta a cada
    foto. Entrada: {idx_foto: [embedding por rostro]}. Salida:
    {idx_foto: [ids de identidad presentes]}. Fotos sin rostro no aparecen.
    """
    flat, owners = [], []
    for idx, embs in embs_by_photo.items():
        for e in embs:
            if e is not None:
                flat.append(e)
                owners.append(idx)
    ids = group_identities(flat, threshold)
    out: dict = {}
    for owner, ident in zip(owners, ids):
        if ident >= 0:
            out.setdefault(owner, set()).add(ident)
    return {k: sorted(v) for k, v in out.items()}
