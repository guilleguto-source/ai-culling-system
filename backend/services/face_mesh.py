"""
face_mesh.py — Atributos faciales con MediaPipe FaceLandmarker (Fase G1).

Arquitectura híbrida, validada sobre el evento real:
  YuNet encuentra las caras (incluso pequeñas)  →  MediaPipe analiza cada
  recorte ampliado (necesita la cara grande y con contexto; sobre la foto
  completa no ve las caras chicas).

Sustituye a eye_state.onnx, cuyo criterio era inservible sobre estas fotos
(el mismo ojo daba 0.00 u 0.87 según el recorte; 97% de falsos "cerrado").
Aquí el EAR es geometría auditable — si falla, se ve por qué — y los
blendshapes dan una segunda señal independiente que debe concordar.

Bonus medido: si MediaPipe no encuentra una cara dentro del recorte, la
detección de YuNet era basura (decoración, muñecos) → filtro de validez gratis.
"""
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent.parent / "models" / "face_landmarker.task"

# Índices estándar de FaceMesh (468 puntos)
_LEFT_EYE = dict(h=(33, 133), v1=(160, 144), v2=(158, 153))
_RIGHT_EYE = dict(h=(362, 263), v1=(385, 380), v2=(387, 373))
_LEFT_CHEEK, _RIGHT_CHEEK, _NOSE_TIP = 234, 454, 1

CROP_SIZE = 384          # a cuánto se amplía el recorte de cara
CROP_MARGIN = 0.6        # margen alrededor del bbox (MediaPipe necesita contexto)

# Umbrales iniciales — a calibrar con la vista de calibración (Fase G2).
EAR_CLOSED = 0.18        # EAR por debajo = ojo cerrado
BLINK_CLOSED = 0.5       # blendshape eyeBlink por encima = ojo cerrado
GAZE_OUT = 0.35          # mira fuera de cámara
SMILE_MIN = 0.35         # sonrisa

_landmarker = None
_failed = False


@dataclass
class FaceAttributes:
    """Atributos de UNA cara. `valid=False` = YuNet detectó algo que no es cara."""
    valid: bool = False
    ear: float = 0.0            # eye aspect ratio (geometría)
    blink: float = 0.0          # blendshape eyeBlink (señal independiente)
    smile: float = 0.0
    gaze_out: float = 0.0
    yaw: float = 0.0            # giro de cabeza; 0 = frontal

    @property
    def eyes_closed(self) -> bool:
        """Cerrado solo si AMBAS señales lo indican: la geometría manda y el
        blendshape confirma. Evita el falso positivo de una sola métrica."""
        return self.valid and (self.ear < EAR_CLOSED or self.blink > BLINK_CLOSED)

    @property
    def looking_away(self) -> bool:
        return self.valid and (self.gaze_out > GAZE_OUT or abs(self.yaw) > 0.5)

    @property
    def smiling(self) -> bool:
        return self.valid and self.smile > SMILE_MIN


# Nº de señales geométricas que se le dan al clasificador híbrido (G3).
FEATURE_DIM = 5


def feature_vector(a: "FaceAttributes") -> np.ndarray:
    """
    Vector geométrico por-cara para el clasificador híbrido (G3). Son las mismas
    señales auditables que usa G1: dárselas al modelo junto al embedding CLIP le
    aporta el detalle fino (un ojo entrecerrado son unos píxeles) que el
    embedding del recorte no resuelve bien. El orden es fijo — debe coincidir
    entre entrenamiento e inferencia.
    """
    return np.array([a.ear, a.blink, a.smile, a.gaze_out, a.yaw], dtype=np.float32)


def to_dict(a: "FaceAttributes") -> dict:
    """Serializa para persistir en el análisis (JSON)."""
    return {"valid": a.valid, "ear": round(a.ear, 4), "blink": round(a.blink, 4),
            "smile": round(a.smile, 4), "gaze_out": round(a.gaze_out, 4),
            "yaw": round(a.yaw, 4)}


def from_dict(d: dict) -> "FaceAttributes":
    return FaceAttributes(
        valid=bool(d.get("valid")), ear=float(d.get("ear", 0.0)),
        blink=float(d.get("blink", 0.0)), smile=float(d.get("smile", 0.0)),
        gaze_out=float(d.get("gaze_out", 0.0)), yaw=float(d.get("yaw", 0.0)),
    )


def uncertainty(a: "FaceAttributes", attribute: str) -> float:
    """
    Cuán dudosa está la predicción (0 = segura, 1 = en el filo del umbral).
    Sirve para preguntar primero las caras que más información aportan:
    100 etiquetas elegidas así valen por ~500 al azar.
    """
    if not a.valid:
        return 0.0
    if attribute == "eyes":
        # distancia relativa al umbral de EAR, y desacuerdo entre las dos señales
        d = abs(a.ear - EAR_CLOSED) / EAR_CLOSED
        geom_dice_cerrado = a.ear < EAR_CLOSED
        blend_dice_cerrado = a.blink > BLINK_CLOSED
        desacuerdo = 1.0 if geom_dice_cerrado != blend_dice_cerrado else 0.0
        return max(0.0, min(1.0, 1.0 - d)) * 0.5 + desacuerdo * 0.5
    if attribute == "gaze":
        d = abs(a.gaze_out - GAZE_OUT) / GAZE_OUT
        return max(0.0, min(1.0, 1.0 - d))
    if attribute == "mouth":
        d = abs(a.smile - SMILE_MIN) / SMILE_MIN
        return max(0.0, min(1.0, 1.0 - d))
    return 0.0


def predict(a: "FaceAttributes", attribute: str) -> str:
    """Etiqueta que G1 propone (se pre-marca en la UI; el usuario corrige)."""
    if not a.valid:
        return ""
    if attribute == "eyes":
        return "cerrados" if a.eyes_closed else "abiertos"
    if attribute == "gaze":
        return "fuera" if a.looking_away else "camara"
    if attribute == "mouth":
        return "sonrisa" if a.smiling else "neutra"
    return ""


def is_available() -> bool:
    return _get_landmarker() is not None


def _get_landmarker():
    global _landmarker, _failed
    if _landmarker is not None:
        return _landmarker
    if _failed or not MODEL_PATH.exists():
        if not MODEL_PATH.exists() and not _failed:
            logger.warning(
                f"face_landmarker.task no encontrado en {MODEL_PATH}. "
                "Los atributos faciales quedan desactivados (ver models/README.md)."
            )
            _failed = True
        return None
    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,                       # una por recorte
            output_face_blendshapes=True,
            min_face_detection_confidence=0.2,  # el recorte ya viene de YuNet
        )
        _landmarker = vision.FaceLandmarker.create_from_options(opts)
        logger.info("MediaPipe FaceLandmarker cargado.")
        return _landmarker
    except Exception as e:
        logger.error(f"No se pudo cargar MediaPipe FaceLandmarker: {e}")
        _failed = True
        return None


def _ear(pts: np.ndarray, eye: dict) -> float:
    h = np.linalg.norm(pts[eye["h"][0]] - pts[eye["h"][1]])
    if h <= 0:
        return 0.0
    v1 = np.linalg.norm(pts[eye["v1"][0]] - pts[eye["v1"][1]])
    v2 = np.linalg.norm(pts[eye["v2"][0]] - pts[eye["v2"][1]])
    return float((v1 + v2) / (2.0 * h))


def _yaw(pts: np.ndarray) -> float:
    n = pts[_NOSE_TIP]
    dl = np.linalg.norm(n - pts[_LEFT_CHEEK])
    dr = np.linalg.norm(n - pts[_RIGHT_CHEEK])
    return float((dl - dr) / (dl + dr)) if (dl + dr) > 0 else 0.0


def analyze_face(img_rgb: np.ndarray, bbox: list[int]) -> FaceAttributes:
    """Analiza UNA cara a partir de su bbox de YuNet."""
    lm = _get_landmarker()
    if lm is None or img_rgb is None or img_rgb.size == 0:
        return FaceAttributes()

    import mediapipe as mp

    h, w = img_rgb.shape[:2]
    x, y, fw, fh = bbox
    m = int(max(fw, fh) * CROP_MARGIN)
    x1, y1 = max(0, x - m), max(0, y - m)
    x2, y2 = min(w, x + fw + m), min(h, y + fh + m)
    crop = img_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return FaceAttributes()

    try:
        crop = cv2.resize(crop, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_CUBIC)
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(crop)))
    except Exception as e:
        logger.debug(f"MediaPipe falló en un recorte: {e}")
        return FaceAttributes()

    if not res.face_landmarks:
        return FaceAttributes()      # no es una cara real: YuNet se equivocó

    pts = np.array([[p.x * CROP_SIZE, p.y * CROP_SIZE] for p in res.face_landmarks[0]])
    bs = {}
    if res.face_blendshapes:
        bs = {b.category_name: b.score for b in res.face_blendshapes[0]}

    return FaceAttributes(
        valid=True,
        ear=(_ear(pts, _LEFT_EYE) + _ear(pts, _RIGHT_EYE)) / 2.0,
        blink=max(bs.get("eyeBlinkLeft", 0.0), bs.get("eyeBlinkRight", 0.0)),
        smile=max(bs.get("mouthSmileLeft", 0.0), bs.get("mouthSmileRight", 0.0)),
        gaze_out=max(bs.get("eyeLookOutLeft", 0.0), bs.get("eyeLookOutRight", 0.0)),
        yaw=_yaw(pts),
    )


def analyze_faces(img_rgb: np.ndarray, face_bboxes: list[list[int]],
                  max_faces: int = 8) -> list[FaceAttributes]:
    """
    Analiza las caras de una foto, de mayor a menor. `max_faces` acota el coste
    en fotos con muchas detecciones (las caras diminutas del fondo no deciden
    si una foto se descarta).
    Retorna la lista en el MISMO orden que face_bboxes (las no analizadas
    quedan como FaceAttributes() con valid=False).
    """
    if not face_bboxes or not is_available():
        return [FaceAttributes() for _ in face_bboxes]

    orden = sorted(range(len(face_bboxes)),
                   key=lambda i: -(face_bboxes[i][2] * face_bboxes[i][3]))
    out = [FaceAttributes() for _ in face_bboxes]
    for i in orden[:max_faces]:
        out[i] = analyze_face(img_rgb, face_bboxes[i])
    return out
