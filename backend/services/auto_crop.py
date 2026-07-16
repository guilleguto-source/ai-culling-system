"""
auto_crop.py — Propuesta de reencuadre no destructivo (geometría pura).
Calcula un crop (fracciones 0..1 + ángulo) que luego se escribe como
crs:Crop* en el XMP: Lightroom lo muestra aplicado y es 100% reversible.

Reglas (spec 2026-07-15-auto-crop-design.md):
- Grupos (≥3 rostros): SOLO nivelar horizonte, sin recomposición.
- Retratos (1-2 rostros): nivelado + rostro dominante a tercios + espacio de mirada.
- Detalles (sin rostros): nivelado + saliencia a tercios.
- La proporción original se conserva SIEMPRE.
"""
import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Límites por nivel: máximo % lineal removible por dimensión
LEVEL_LIMITS = {"minimo": 0.10, "medio": 0.20, "agresivo": 0.35}

MAX_LEVEL_ANGLE = 7.0      # grados; más inclinación = holandés intencional o error
ROTATION_CROP_PER_DEG = 0.015  # recorte lineal que consume nivelar 1 grado
MAX_ROTATION_CROP = 0.08   # si nivelar exige más que esto, no se nivela
MIN_CHANGE = 0.02          # cambio lineal mínimo para proponer crop
MIN_ANGLE = 0.5            # grados; menos = no vale la pena nivelar
FACE_EDGE_MARGIN = 0.5     # margen de seguridad: 0.5x el tamaño del rostro
GAZE_AIR_RATIO = 2.0 / 3.0 # fracción del aire hacia donde mira el sujeto

# Puntos fuertes: tercios (siempre) y áurea (solo nivel agresivo)
THIRDS = (1.0 / 3.0, 2.0 / 3.0)
GOLDEN = (0.382, 0.618)

# Detección de horizonte
_HORIZON_MAX_TILT = 15.0   # solo líneas casi horizontales
_HORIZON_MIN_LEN = 0.25    # longitud mínima relativa al ancho


@dataclass
class CropProposal:
    """Bordes internos del crop en fracciones de la imagen (0..1) + ángulo."""
    left: float = 0.0
    top: float = 0.0
    right: float = 1.0
    bottom: float = 1.0
    angle: float = 0.0     # grados; positivo = girar horario para nivelar
    reason: str = ""

    @property
    def crop_amount(self) -> float:
        """Máximo % lineal removido entre ambas dimensiones."""
        return max(self.left + (1.0 - self.right), self.top + (1.0 - self.bottom))

    def is_meaningful(self) -> bool:
        return self.crop_amount >= MIN_CHANGE or abs(self.angle) >= MIN_ANGLE

    def to_dict(self) -> dict:
        return {
            "left": round(self.left, 4), "top": round(self.top, 4),
            "right": round(self.right, 4), "bottom": round(self.bottom, 4),
            "angle": round(self.angle, 2), "reason": self.reason,
        }


def detect_horizon_angle(img_gray: np.ndarray) -> float | None:
    """
    Ángulo de inclinación del horizonte en grados (positivo = horizonte cae a
    la derecha). None si no hay líneas suficientemente largas y horizontales.
    """
    h, w = img_gray.shape[:2]
    if w < 100 or h < 100:
        return None
    edges = cv2.Canny(img_gray, 50, 150)
    min_len = int(w * _HORIZON_MIN_LEN)
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=80,
        minLineLength=min_len, maxLineGap=int(w * 0.02),
    )
    if lines is None:
        return None

    candidates = []  # (ángulo, longitud)
    for (x1, y1, x2, y2) in lines[:, 0]:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < min_len:
            continue
        ang = math.degrees(math.atan2(dy, dx))
        # Normalizar a [-90, 90]
        if ang > 90:
            ang -= 180
        elif ang < -90:
            ang += 180
        if abs(ang) <= _HORIZON_MAX_TILT:
            candidates.append((ang, length))

    if not candidates:
        return None
    # Mediana ponderada por longitud
    candidates.sort(key=lambda c: c[0])
    total = sum(l for _, l in candidates)
    acc = 0.0
    for ang, l in candidates:
        acc += l
        if acc >= total / 2:
            return float(ang)
    return float(candidates[-1][0])


def _leveling_angle(horizon_angle: float | None) -> float:
    """Ángulo de corrección aplicable (0 si no procede nivelar)."""
    if horizon_angle is None or abs(horizon_angle) < MIN_ANGLE:
        return 0.0
    if abs(horizon_angle) > MAX_LEVEL_ANGLE:
        return 0.0
    if abs(horizon_angle) * ROTATION_CROP_PER_DEG > MAX_ROTATION_CROP:
        return 0.0
    # Girar en sentido contrario a la inclinación para nivelar
    return -horizon_angle


def _rotation_crop(angle: float) -> float:
    """Recorte lineal que consume la rotación (estimación conservadora)."""
    return abs(angle) * ROTATION_CROP_PER_DEG


def _faces_inside(window: tuple[float, float, float, float],
                  face_bboxes: list[list[int]], w: int, h: int) -> bool:
    """True si todos los rostros (con margen de seguridad) caen dentro del crop."""
    wl, wt, wr, wb = window
    for (x, y, fw, fh) in face_bboxes:
        mx, my = fw * FACE_EDGE_MARGIN, fh * FACE_EDGE_MARGIN
        if ((x - mx) / w < wl or (y - my) / h < wt
                or (x + fw + mx) / w > wr or (y + fh + my) / h > wb):
            return False
    return True


def _nearest_strong_point(fx: float, fy: float, level: str) -> tuple[float, float]:
    """Punto fuerte (tercios; agresivo también áurea) más cercano al sujeto."""
    lines = list(THIRDS)
    if level == "agresivo":
        lines += list(GOLDEN)
    tx = min(lines, key=lambda v: abs(v - fx))
    ty = min(lines, key=lambda v: abs(v - fy))
    return tx, ty


def _gaze_target_x(dominant_face_landmarks: list[list[int]] | None,
                   face_center_x: float, default_tx: float) -> float:
    """
    Ajusta la línea vertical objetivo según la mirada: el aire va hacia donde
    apunta la nariz. Nariz a la izquierda del centro de ojos → mira izquierda
    → sujeto al tercio derecho (aire a la izquierda), y viceversa.
    """
    if not dominant_face_landmarks or len(dominant_face_landmarks) < 3:
        return default_tx
    left_eye, right_eye, nose = dominant_face_landmarks[0], dominant_face_landmarks[1], dominant_face_landmarks[2]
    eyes_cx = (left_eye[0] + right_eye[0]) / 2.0
    eye_dist = max(1.0, abs(right_eye[0] - left_eye[0]))
    offset = (nose[0] - eyes_cx) / eye_dist
    if abs(offset) < 0.08:          # mirada frontal: mantener el punto más cercano
        return default_tx
    return THIRDS[1] if offset < 0 else THIRDS[0]  # mira izq → sujeto a la derecha


def _recompose(subject: tuple[float, float], target: tuple[float, float],
               budget: float, face_bboxes: list[list[int]],
               w: int, h: int) -> tuple[float, float, float, float] | None:
    """
    Ventana (left, top, right, bottom) que acerca al sujeto al punto objetivo
    con el menor recorte posible, sin exceder `budget` ni cortar rostros.
    """
    sx, sy = subject
    tx, ty = target
    # Probar recortes crecientes: el primero que alcanza el objetivo gana.
    for c in [round(x, 3) for x in np.arange(0.02, budget + 1e-9, 0.01)]:
        s = 1.0 - c   # escala de la ventana (misma en ambas dims → aspecto intacto)
        # Posición ideal: el sujeto cae en (tx, ty) dentro de la ventana
        wl = min(max(sx - tx * s, 0.0), c)
        wt = min(max(sy - ty * s, 0.0), c)
        window = (wl, wt, wl + s, wt + s)
        achieved_x = (sx - wl) / s
        achieved_y = (sy - wt) / s
        if abs(achieved_x - tx) < 0.02 and abs(achieved_y - ty) < 0.02:
            if _faces_inside(window, face_bboxes, w, h):
                return window
            return None  # el crop que logra el objetivo corta un rostro
    # No alcanzable dentro del presupuesto: usar el máximo acercamiento posible
    s = 1.0 - budget
    wl = min(max(sx - tx * s, 0.0), budget)
    wt = min(max(sy - ty * s, 0.0), budget)
    window = (wl, wt, wl + s, wt + s)
    if _faces_inside(window, face_bboxes, w, h):
        return window
    return None


def propose_crop(
    scene_type: str,
    face_bboxes: list[list[int]],
    eye_landmarks: list[list[list[int]]],
    saliency_region: tuple[int, int, int, int] | None,
    img_shape: tuple[int, int],
    level: str,
    horizon_angle: float | None = None,
) -> CropProposal | None:
    """
    Propone un reencuadre según el tipo de escena y el nivel configurado.
    Retorna None si no hay mejora que valga la pena o si es inseguro.
    """
    if level not in LEVEL_LIMITS:
        return None
    h, w = img_shape[:2]
    if h < 3 or w < 3:
        return None

    angle = _leveling_angle(horizon_angle)
    rot_crop = _rotation_crop(angle)

    # --- Grupos: solo nivelado, recorte simétrico mínimo para la rotación ---
    if len(face_bboxes) >= 3:
        if angle == 0.0:
            return None
        half = rot_crop / 2.0
        prop = CropProposal(half, half, 1.0 - half, 1.0 - half, angle, "nivelado (grupo)")
        return prop if prop.is_meaningful() else None

    budget = max(0.0, LEVEL_LIMITS[level] - rot_crop)

    # --- Sujeto y objetivo ---
    if face_bboxes:  # retrato / pareja
        dominant_i = max(range(len(face_bboxes)), key=lambda i: face_bboxes[i][2] * face_bboxes[i][3])
        x, y, fw, fh = face_bboxes[dominant_i]
        subject = ((x + fw / 2.0) / w, (y + fh / 2.0) / h)
        target = _nearest_strong_point(*subject, level)
        lms = eye_landmarks[dominant_i] if dominant_i < len(eye_landmarks) else None
        target = (_gaze_target_x(lms, subject[0], target[0]), target[1])
        reason = "tercios + mirada"
    elif saliency_region is not None:  # detalle
        sx, sy, sw, sh = saliency_region
        subject = ((sx + sw / 2.0) / w, (sy + sh / 2.0) / h)
        target = _nearest_strong_point(*subject, level)
        reason = "saliencia a tercios"
    else:
        # Sin sujeto detectable: a lo sumo nivelar
        if angle == 0.0:
            return None
        half = rot_crop / 2.0
        prop = CropProposal(half, half, 1.0 - half, 1.0 - half, angle, "nivelado")
        return prop if prop.is_meaningful() else None

    window = None
    if budget >= MIN_CHANGE and (abs(subject[0] - target[0]) > 0.02 or abs(subject[1] - target[1]) > 0.02):
        window = _recompose(subject, target, budget, face_bboxes, w, h)

    if window is None:
        if angle == 0.0:
            return None
        half = rot_crop / 2.0
        window = (half, half, 1.0 - half, 1.0 - half)
        reason = "nivelado"
    elif rot_crop > 0:
        reason += " + nivelado"

    prop = CropProposal(*window, angle, reason)
    return prop if prop.is_meaningful() else None
