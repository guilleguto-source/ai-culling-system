import logging
from pathlib import Path
import cv2
import numpy as np

from services.app_paths import get_models_dir as _get_models_dir

logger = logging.getLogger(__name__)

MODELS_DIR = _get_models_dir()
ONNX_MODEL_PATH = MODELS_DIR / "blink_detector.onnx"

_session = None
_available = None

def is_available() -> bool:
    global _available
    if _available is not None:
        return _available

    if not ONNX_MODEL_PATH.exists():
        _available = False
        return False

    try:
        import onnxruntime as ort
        global _session
        _session = ort.InferenceSession(str(ONNX_MODEL_PATH), providers=['CPUExecutionProvider'])
        _available = True
        return True
    except ImportError:
        logger.warning("onnxruntime no está instalado. Fallback a MediaPipe para parpadeos.")
        _available = False
        return False
    except Exception as e:
        logger.error(f"Error cargando modelo ONNX de parpadeos: {e}")
        _available = False
        return False

def _crop_eye(image: np.ndarray, face_bbox: tuple, eye_landmark: tuple, padding: float = 0.5) -> np.ndarray | None:
    """Extrae la región del ojo asumiendo una proporción del tamaño de la cara."""
    x, y, w, h = face_bbox
    ex, ey = eye_landmark
    
    # Tamaño del recorte estimado
    eye_w = int(w * 0.25)
    eye_h = int(eye_w * 0.75)
    
    x1 = int(ex - eye_w / 2)
    y1 = int(ey - eye_h / 2)
    x2 = x1 + eye_w
    y2 = y1 + eye_h
    
    # Límites
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
    
    if x2 <= x1 or y2 <= y1:
        return None
        
    eye_crop = image[y1:y2, x1:x2]
    return eye_crop

def predict_eyes_open(image: np.ndarray, face_bboxes: list, eye_landmarks: list) -> list[float]:
    """
    Recibe la imagen completa y devuelve la probabilidad [0..1] de ojos abiertos
    para cada rostro detectado.
    Si no hay landmarks, o la inferencia falla, retorna 0.5.
    """
    if not is_available() or _session is None:
        return [0.5] * len(face_bboxes)
        
    probs = []
    input_name = _session.get_inputs()[0].name
    
    for i, bbox in enumerate(face_bboxes):
        if i >= len(eye_landmarks):
            probs.append(0.5)
            continue
            
        # Landmarks suele tener [left_eye, right_eye, nose, mouth_left, mouth_right]
        # Promediamos o iteramos. Para simplificar, recortamos alrededor de los dos ojos.
        # eye_landmarks[i] es una lista de puntos (x, y). Los primeros 2 son ojos.
        pts = eye_landmarks[i]
        if len(pts) < 2:
            probs.append(0.5)
            continue
            
        left_eye, right_eye = pts[0], pts[1]
        
        # Recorte y predicción ojo izquierdo
        crop_l = _crop_eye(image, bbox, left_eye)
        crop_r = _crop_eye(image, bbox, right_eye)
        
        eye_probs = []
        for crop in (crop_l, crop_r):
            if crop is None or crop.size == 0:
                continue
            
            # Preprocesamiento típico para ONNX (dependerá del modelo real)
            # Asumimos 64x64, RGB, normalizado a 0-1
            resized = cv2.resize(crop, (64, 64))
            blob = resized.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1)) # HWC a CHW
            blob = np.expand_dims(blob, axis=0)  # NCHW
            
            try:
                out = _session.run(None, {input_name: blob})[0]
                # out[0] podría ser prob(abierto), prob(cerrado). Asumimos out[0][0] es prob(abierto)
                # O un escalar logit. Lo dejamos genérico como un valor sigmoid [0..1].
                prob = float(out[0][0] if out.shape[1] > 1 else out[0])
                eye_probs.append(prob)
            except Exception:
                pass
                
        # Si un ojo está cerrado, consideramos parpadeo
        if eye_probs:
            probs.append(min(eye_probs))
        else:
            probs.append(0.5)
            
    return probs
