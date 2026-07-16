"""
person_detector.py — Detección de PERSONAS (cuerpos completos) con YOLOv8n ONNX.
Complementa a YuNet: detecta gente de espaldas, de perfil o parcialmente en
cuadro (sin rostro visible), para que el auto-crop nunca corte a nadie.

Degradación: sin el modelo descargado, is_available() es False y el crop
usa solo las cajas derivadas de rostros (comportamiento anterior).
"""
import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL_PATH = MODELS_DIR / "person_yolov8n.onnx"

INPUT_SIZE = 640
CONF_THRESHOLD = 0.35
NMS_THRESHOLD = 0.45
PERSON_CLASS = 0

_session = None
_session_failed = False


def is_available() -> bool:
    return _get_session() is not None


def _get_session():
    global _session, _session_failed
    if _session is not None:
        return _session
    if _session_failed or not MODEL_PATH.exists():
        if not MODEL_PATH.exists() and not _session_failed:
            logger.warning(
                f"Modelo de personas no encontrado en {MODEL_PATH}. "
                "El auto-crop protegerá solo cuerpos derivados de rostros "
                "(ver models/README.md para descargarlo)."
            )
            _session_failed = True
        return None
    try:
        import onnxruntime as ort
        _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
        logger.info("Detector de personas YOLOv8n cargado.")
        return _session
    except Exception as e:
        logger.error(f"No se pudo cargar el detector de personas: {e}")
        _session_failed = True
        return None


def detect_persons(img_rgb: np.ndarray) -> list[list[int]]:
    """
    Detecta personas y retorna bboxes [x, y, w, h] en pixeles de la imagen.
    Lista vacía si el modelo no está disponible o no hay personas.
    """
    session = _get_session()
    if session is None or img_rgb is None or img_rgb.size == 0:
        return []

    h0, w0 = img_rgb.shape[:2]
    # Letterbox a 640x640 preservando aspecto
    scale = INPUT_SIZE / max(h0, w0)
    nh, nw = round(h0 * scale), round(w0 * scale)
    resized = cv2.resize(img_rgb, (nw, nh))
    canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    canvas[:nh, :nw] = resized
    x = canvas.astype(np.float32).transpose(2, 0, 1)[np.newaxis] / 255.0

    try:
        out = session.run(None, {session.get_inputs()[0].name: x})[0]
    except Exception as e:
        logger.error(f"Error en detección de personas: {e}")
        return []

    # YOLOv8: (1, 4+nc, 8400) → filas: cx, cy, w, h, scores...
    pred = out[0]
    boxes_cxcywh = pred[:4].T                 # (8400, 4)
    person_scores = pred[4 + PERSON_CLASS]    # (8400,)

    mask = person_scores >= CONF_THRESHOLD
    if not mask.any():
        return []
    boxes_cxcywh = boxes_cxcywh[mask]
    scores = person_scores[mask]

    # cxcywh → xywh (en espacio letterbox)
    xywh = np.empty_like(boxes_cxcywh)
    xywh[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
    xywh[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
    xywh[:, 2:] = boxes_cxcywh[:, 2:]

    keep = cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), CONF_THRESHOLD, NMS_THRESHOLD)
    if len(keep) == 0:
        return []

    result = []
    for i in np.array(keep).ravel():
        bx, by, bw, bh = xywh[i] / scale       # de letterbox a imagen original
        x1 = max(0, int(bx))
        y1 = max(0, int(by))
        x2 = min(w0, int(bx + bw))
        y2 = min(h0, int(by + bh))
        if x2 > x1 and y2 > y1:
            result.append([x1, y1, x2 - x1, y2 - y1])
    return result
