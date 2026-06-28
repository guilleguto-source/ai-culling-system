"""
face_assessment.py — Evaluación biométrica de rostros.
Detecta ojos cerrados y expresiones usando modelos ONNX.
Solo se ejecuta en imágenes clasificadas como RETRATO (con rostros detectados).
"""
import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Umbral de probabilidad para clasificar un ojo como "cerrado"
# (OCEC: cerrado cuando prob_open <= 0.42, i.e. prob_closed >= 0.58)
EYE_CLOSED_THRESHOLD = 0.58

# Índices de landmarks de YuNet: [ojo_izq, ojo_der, nariz, boca_izq, boca_der]
LANDMARK_LEFT_EYE = 0
LANDMARK_RIGHT_EYE = 1


@dataclass
class FaceAssessmentResult:
    face_index: int
    has_closed_eyes: bool
    left_eye_closed_prob: float
    right_eye_closed_prob: float
    eye_aspect_ratio: float        # EAR — proxy rápido sin modelo ONNX
    used_onnx_model: bool = False


@dataclass
class ImageFaceResult:
    face_count: int
    any_closed_eyes: bool
    face_results: list[FaceAssessmentResult] = field(default_factory=list)


# --- Método rápido: Eye Aspect Ratio (EAR) sin modelo ONNX ---

def _eye_aspect_ratio_from_patch(eye_patch_gray: np.ndarray) -> float:
    """
    Estimación rápida del estado del ojo por análisis de gradiente vertical.
    Un ojo abierto tiene una transición clara entre iris oscuro y esclerótica clara.
    Un ojo cerrado es uniforme (sin transición marcada).

    Retorna un score 0-1: valores bajos = cerrado, valores altos = abierto.
    """
    if eye_patch_gray.size == 0:
        return 0.5  # Indeterminado

    h, w = eye_patch_gray.shape
    # Dividir el parche en tercio superior, medio e inferior
    top = eye_patch_gray[:h // 3, :]
    mid = eye_patch_gray[h // 3: 2 * h // 3, :]
    bot = eye_patch_gray[2 * h // 3:, :]

    # En un ojo abierto, el centro (iris) suele ser más oscuro que arriba/abajo
    contrast = (float(np.mean(top)) + float(np.mean(bot))) / 2.0 - float(np.mean(mid))
    # Normalizar a [0, 1]
    score = min(1.0, max(0.0, contrast / 60.0))
    return score


def _extract_eye_patch(
    img_gray: np.ndarray,
    landmark: list[int],
    patch_size: int = 32,
) -> np.ndarray:
    """Recorta un parche cuadrado centrado en el punto de landmark del ojo."""
    cx, cy = landmark[0], landmark[1]
    half = patch_size // 2
    h, w = img_gray.shape
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(w, cx + half)
    y2 = min(h, cy + half)
    return img_gray[y1:y2, x1:x2]


def evaluate_eyes_fast(
    img_rgb: np.ndarray,
    eye_landmarks: list[list[list[int]]],  # Por rostro: [[x,y] x 5 landmarks]
) -> ImageFaceResult:
    """
    Evaluación rápida de ojos usando análisis de gradiente (sin modelo ONNX).
    Útil como fallback cuando no hay modelo eye_state.onnx disponible.

    Args:
        img_rgb: Imagen completa en RGB.
        eye_landmarks: Lista por rostro de los 5 landmarks de YuNet.

    Returns:
        ImageFaceResult con el estado de los ojos por rostro.
    """
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    face_results = []
    any_closed = False

    for i, landmarks in enumerate(eye_landmarks):
        if len(landmarks) < 2:
            continue

        left_patch = _extract_eye_patch(img_gray, landmarks[LANDMARK_LEFT_EYE])
        right_patch = _extract_eye_patch(img_gray, landmarks[LANDMARK_RIGHT_EYE])

        left_score = _eye_aspect_ratio_from_patch(left_patch)
        right_score = _eye_aspect_ratio_from_patch(right_patch)

        avg_ear = (left_score + right_score) / 2.0
        left_closed = left_score < (1.0 - EYE_CLOSED_THRESHOLD)
        right_closed = right_score < (1.0 - EYE_CLOSED_THRESHOLD)
        has_closed = left_closed or right_closed

        if has_closed:
            any_closed = True
            logger.debug(
                f"Rostro {i}: ojos cerrados detectados "
                f"(izq={left_score:.2f}, der={right_score:.2f})"
            )

        face_results.append(FaceAssessmentResult(
            face_index=i,
            has_closed_eyes=has_closed,
            left_eye_closed_prob=1.0 - left_score,
            right_eye_closed_prob=1.0 - right_score,
            eye_aspect_ratio=avg_ear,
            used_onnx_model=False,
        ))

    return ImageFaceResult(
        face_count=len(face_results),
        any_closed_eyes=any_closed,
        face_results=face_results,
    )


def evaluate_eyes_onnx(
    img_rgb: np.ndarray,
    eye_landmarks: list[list[list[int]]],
    onnx_session,
) -> ImageFaceResult:
    """
    Evaluación de ojos usando un modelo ONNX de clasificación (cuando está disponible).
    El modelo debe aceptar parches de ojo (32x32x3) y retornar [prob_abierto, prob_cerrado].

    Args:
        img_rgb: Imagen completa en RGB.
        eye_landmarks: Lista por rostro de los 5 landmarks de YuNet.
        onnx_session: Sesión ONNX Runtime del clasificador de ojos.

    Returns:
        ImageFaceResult con el estado de los ojos por rostro.
    """
    face_results = []
    any_closed = False

    # Tamaño de entrada del modelo (OCEC: 24x40). Salida: prob_open (sigmoide única).
    inp = onnx_session.get_inputs()[0]
    in_name = inp.name
    ih, iw = (int(inp.shape[2]), int(inp.shape[3])) if len(inp.shape) == 4 else (24, 40)

    for i, landmarks in enumerate(eye_landmarks):
        if len(landmarks) < 2:
            continue

        h, w = img_rgb.shape[:2]
        lx, ly = landmarks[LANDMARK_LEFT_EYE]
        rx, ry = landmarks[LANDMARK_RIGHT_EYE]
        eye_dist = max(8.0, ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5)
        half = max(8, int(eye_dist * 0.35))   # recorte relativo a la cara (independiente de la resolución)

        probs_closed = []
        for cx, cy in (landmarks[LANDMARK_LEFT_EYE], landmarks[LANDMARK_RIGHT_EYE]):
            x1, y1 = max(0, cx - half), max(0, cy - half)
            x2, y2 = min(w, cx + half), min(h, cy + half)
            patch = img_rgb[y1:y2, x1:x2]
            if patch.size == 0:
                probs_closed.append(0.5)
                continue
            patch_resized = cv2.resize(patch, (iw, ih)).astype(np.float32) / 255.0
            patch_input = patch_resized.transpose(2, 0, 1)[np.newaxis, ...]  # NCHW
            output = onnx_session.run(None, {in_name: patch_input})[0]
            prob_open = float(np.clip(np.ravel(output)[0], 0.0, 1.0))
            probs_closed.append(1.0 - prob_open)   # OCEC da prob_open; cerrado = 1 - open

        left_prob_closed, right_prob_closed = probs_closed[0], probs_closed[1]
        has_closed = (
            left_prob_closed > EYE_CLOSED_THRESHOLD or
            right_prob_closed > EYE_CLOSED_THRESHOLD
        )
        if has_closed:
            any_closed = True

        face_results.append(FaceAssessmentResult(
            face_index=i,
            has_closed_eyes=has_closed,
            left_eye_closed_prob=left_prob_closed,
            right_eye_closed_prob=right_prob_closed,
            eye_aspect_ratio=(1 - left_prob_closed + 1 - right_prob_closed) / 2.0,
            used_onnx_model=True,
        ))

    return ImageFaceResult(
        face_count=len(face_results),
        any_closed_eyes=any_closed,
        face_results=face_results,
    )
