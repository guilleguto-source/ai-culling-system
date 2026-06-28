"""
scene_classifier.py — Clasificador de escena: bifurcación entre RETRATO y DETALLE/OBJETO.
Si se detectan rostros → modo retrato (evalúa ojos, expresiones).
Si NO hay rostros → modo detalle/objeto (evalúa nitidez por saliencia, NO penaliza por ausencia de personas).
"""
import logging
from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SceneType(str, Enum):
    PORTRAIT = "portrait"    # Hay personas/rostros detectables
    DETAIL = "detail"        # Objetos, manos, decoración, macros — sin rostros


@dataclass
class SceneResult:
    scene_type: SceneType
    face_count: int
    face_bboxes: list[list[int]]    # [[x, y, w, h], ...]
    eye_landmarks: list[list]       # Puntos de referencia de ojos por rostro
    confidence: float               # Confianza promedio de la detección


def classify_scene(
    img_rgb: np.ndarray,
    face_detector,                  # YuNet detector de OpenCV
    min_face_confidence: float = 0.6,
) -> SceneResult:
    """
    Clasifica la escena detectando si hay rostros presentes.

    Args:
        img_rgb: Array numpy en formato RGB (H, W, 3).
        face_detector: Instancia del detector YuNet de OpenCV.
        min_face_confidence: Umbral mínimo de confianza para considerar un rostro válido.

    Returns:
        SceneResult con el tipo de escena y datos de rostros si los hay.
    """
    h, w = img_rgb.shape[:2]
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    # Ajustar el tamaño de entrada del detector al tamaño de la imagen
    face_detector.setInputSize((w, h))

    _, detections = face_detector.detect(img_bgr)

    face_bboxes = []
    eye_landmarks = []
    confidences = []

    if detections is not None:
        for det in detections:
            confidence = float(det[-1])
            if confidence < min_face_confidence:
                continue

            # Extraer bounding box [x, y, w, h]
            x, y, fw, fh = int(det[0]), int(det[1]), int(det[2]), int(det[3])
            face_bboxes.append([x, y, fw, fh])
            confidences.append(confidence)

            # Extraer landmarks: índices 4-13 son los 5 puntos faciales (x,y pares)
            # Orden: ojo_izq, ojo_der, nariz, boca_izq, boca_der
            landmarks = []
            for i in range(5):
                lx = int(det[4 + i * 2])
                ly = int(det[4 + i * 2 + 1])
                landmarks.append([lx, ly])
            eye_landmarks.append(landmarks)

    face_count = len(face_bboxes)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    scene_type = SceneType.PORTRAIT if face_count > 0 else SceneType.DETAIL

    logger.debug(
        f"Escena: {scene_type.value} | Rostros: {face_count} | "
        f"Confianza promedio: {avg_confidence:.2f}"
    )

    return SceneResult(
        scene_type=scene_type,
        face_count=face_count,
        face_bboxes=face_bboxes,
        eye_landmarks=eye_landmarks,
        confidence=avg_confidence,
    )


def compute_saliency_region(img_rgb: np.ndarray) -> tuple[int, int, int, int]:
    """
    Calcula la región de mayor saliencia (zona de enfoque del fotógrafo)
    para fotos de DETALLE sin rostros.
    Usa el mapa de gradientes de alta frecuencia (Sobel) para encontrar
    la zona con más detalle/textura = zona enfocada.

    Returns:
        (x, y, w, h) — Bounding box de la región más saliente.
    """
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    # Calcular magnitud del gradiente (detector de bordes Sobel)
    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)

    # Aplicar blur gaussiano para suavizar el mapa de saliencia
    saliency_map = cv2.GaussianBlur(magnitude, (51, 51), 0)

    # Encontrar el punto de máxima saliencia
    _, _, _, max_loc = cv2.minMaxLoc(saliency_map)
    mx, my = max_loc

    h, w = img_rgb.shape[:2]

    # Definir una región centrada en el punto de mayor saliencia
    # Tamaño proporcional a la imagen (25% del ancho y alto)
    rw = max(64, w // 4)
    rh = max(64, h // 4)
    rx = max(0, mx - rw // 2)
    ry = max(0, my - rh // 2)
    rx = min(rx, w - rw)
    ry = min(ry, h - rh)

    return (rx, ry, rw, rh)
