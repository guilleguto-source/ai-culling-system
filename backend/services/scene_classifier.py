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
    face_embeddings: list[np.ndarray | None] # Embeddings ArcFace por rostro
    face_yaws: list[float]          # Yaw por rostro
    face_pitches: list[float]       # Pitch por rostro
    confidence: float               # Confianza promedio de la detección


def classify_scene(
    img_rgb: np.ndarray,
    face_detector,                  # UniFace FaceAnalyzer
    min_face_confidence: float = 0.6,
    gaze_estimator=None,
) -> SceneResult:
    """
    Clasifica la escena detectando si hay rostros presentes.

    Args:
        img_rgb: Array numpy en formato RGB (H, W, 3).
        face_detector: Instancia del detector UniFace FaceAnalyzer.
        min_face_confidence: Umbral mínimo de confianza para considerar un rostro válido.

    Returns:
        SceneResult con el tipo de escena y datos de rostros si los hay.
    """
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    faces = face_detector.analyze(img_bgr) if face_detector else []

    face_bboxes = []
    eye_landmarks = []
    face_embeddings = []
    face_yaws = []
    face_pitches = []
    confidences = []

    for face in faces:
        confidence = float(face.confidence)
        if confidence < min_face_confidence:
            continue

        # Extraer bounding box [x, y, w, h]
        x, y, fw, fh = face.bbox_xywh
        face_bboxes.append([int(x), int(y), int(fw), int(fh)])
        confidences.append(confidence)
        
        # Extraer embedding (ArcFace)
        face_embeddings.append(face.embedding)

        # Extraer landmarks: uniface devuelve un array (5, 2)
        # Orden: ojo_izq, ojo_der, nariz, boca_izq, boca_der
        if face.landmarks is not None and len(face.landmarks) >= 5:
            landmarks = [[int(pt[0]), int(pt[1])] for pt in face.landmarks]
            eye_landmarks.append(landmarks)
        else:
            eye_landmarks.append([])

        # Extraer Gaze si el estimador está disponible
        yaw, pitch = 0.0, 0.0
        if gaze_estimator is not None:
            # Recortar la cara
            x1, y1 = max(0, int(x)), max(0, int(y))
            x2, y2 = min(img_bgr.shape[1], int(x+fw)), min(img_bgr.shape[0], int(y+fh))
            face_crop = img_bgr[y1:y2, x1:x2]
            if face_crop.size > 0:
                try:
                    gaze = gaze_estimator.estimate(face_crop)
                    # Convertir a grados para que sea fácil razonar
                    yaw = np.degrees(gaze.yaw)
                    pitch = np.degrees(gaze.pitch)
                except Exception as e:
                    logger.debug(f"Error estimating gaze: {e}")
        face_yaws.append(yaw)
        face_pitches.append(pitch)

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
        face_embeddings=face_embeddings,
        face_yaws=face_yaws,
        face_pitches=face_pitches,
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
