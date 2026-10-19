"""
bw_recommender.py — Evaluador de idoneidad y recomendación para Blanco y Negro (B&N).

Detecta fotos que funcionan excepcionalmente bien en B&N:
1. Sobreexposición asimétrica por canal (ej. canal Rojo quemado pero Verde/Azul con textura recuperable).
2. Sesiones monocromáticas de color dominante (donde el B&N libera la estructura tonal).
3. Alto contraste tonal / Claroscuro (velas, sombras profundas, altas luces puntuales).
4. Iluminación dramática lateral en retratos (estilo Rembrandt / Split lighting).
"""

import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def compute_bw_recommendation(
    img_rgb: np.ndarray,
    face_bboxes: list[list[int]] | None = None,
) -> tuple[bool, float, list[str]]:
    """
    Evalúa una imagen y calcula un score de idoneidad para conversión a Blanco y Negro.

    Args:
        img_rgb: Imagen en RGB (H, W, 3) tipo uint8.
        face_bboxes: Bounding boxes [[x, y, w, h], ...] de rostros detectados.

    Returns:
        (is_candidate: bool, score: float [0..1], reasons: list[str])
    """
    if img_rgb is None or img_rgb.size == 0:
        return False, 0.0, []

    h, w, c = img_rgb.shape
    if c != 3:
        return False, 0.0, []

    reasons: list[str] = []
    score_accum = 0.0

    r_channel = img_rgb[:, :, 0].astype(np.float32)
    g_channel = img_rgb[:, :, 1].astype(np.float32)
    b_channel = img_rgb[:, :, 2].astype(np.float32)

    total_pixels = float(h * w)

    # ---------------------------------------------------------
    # Señal 1: Sobreexposición asimétrica por canal
    # ---------------------------------------------------------
    # Si un canal (ej. R) está saturado (>245) en >4% de la foto,
    # pero los otros canales (G o B) conservan información (<1.5% saturados),
    # el B&N rescata la textura perdida por empastamiento cromático.
    r_clip = np.sum(r_channel > 245) / total_pixels
    g_clip = np.sum(g_channel > 245) / total_pixels
    b_clip = np.sum(b_channel > 245) / total_pixels

    max_clip = max(r_clip, g_clip, b_clip)
    min_clip = min(r_clip, g_clip, b_clip)

    if max_clip > 0.035 and min_clip < 0.015:
        score_accum += 0.35
        reasons.append("Recuperación de altas luces (canal cromático quemado con textura intacta)")

    # ---------------------------------------------------------
    # Señal 2: Dominancia monocromática
    # ---------------------------------------------------------
    # Escenas donde un solo canal domina fuertemente sobre los demás
    # (>60% de la energía total del color), como fondos y vestuarios rojos monocromáticos.
    mean_r = float(np.mean(r_channel))
    mean_g = float(np.mean(g_channel))
    mean_b = float(np.mean(b_channel))
    sum_means = max(1.0, mean_r + mean_g + mean_b)

    ratio_r = mean_r / sum_means
    ratio_g = mean_g / sum_means
    ratio_b = mean_b / sum_means

    if max(ratio_r, ratio_g, ratio_b) > 0.58:
        score_accum += 0.30
        reasons.append("Escena monocromática (el B&N resalta volumen y siluetas)")

    # ---------------------------------------------------------
    # Señal 3: Alto contraste tonal / Claroscuro (velas, sombras)
    # ---------------------------------------------------------
    # Se mide sobre la luminancia (desviación estándar alta de L en LAB o escala de grises)
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    std_lum = float(np.std(gray))
    p10 = float(np.percentile(gray, 10))
    p90 = float(np.percentile(gray, 90))
    dynamic_spread = p90 - p10

    if std_lum > 58.0 and dynamic_spread > 130.0:
        score_accum += 0.25
        reasons.append("Alto contraste tonal / Claroscuro (iluminación dramática)")

    # ---------------------------------------------------------
    # Señal 4: Iluminación dramática lateral en retratos
    # ---------------------------------------------------------
    if face_bboxes and len(face_bboxes) > 0:
        face_split_contrasts = []
        for (fx, fy, fw, fh) in face_bboxes[:3]:
            fx, fy = max(0, fx), max(0, fy)
            fx2, fy2 = min(w, fx + fw), min(h, fy + fh)
            face_roi = gray[fy:fy2, fx:fx2]
            if face_roi.size > 100:
                mid_x = face_roi.shape[1] // 2
                left_half = face_roi[:, :mid_x]
                right_half = face_roi[:, mid_x:]
                mean_l = float(np.mean(left_half)) + 1e-4
                mean_r_val = float(np.mean(right_half)) + 1e-4
                contrast_ratio = max(mean_l, mean_r_val) / min(mean_l, mean_r_val)
                face_split_contrasts.append(contrast_ratio)

        if face_split_contrasts and max(face_split_contrasts) > 1.75:
            score_accum += 0.25
            reasons.append("Retrato con iluminación lateral dramática (Split / Rembrandt)")

    # Normalizar score a [0.0 .. 1.0]
    final_score = round(min(1.0, score_accum), 2)
    is_candidate = final_score >= 0.55

    return is_candidate, final_score, reasons
