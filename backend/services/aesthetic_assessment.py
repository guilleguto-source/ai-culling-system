"""
aesthetic_assessment.py — Evaluación estética multidimensional heurística (OpenCV).

ROL: FALLBACK FRÍO Y DESEMPATE ESTRUCTURADO.
Evalúa la calidad artística de la imagen a través de 7 ejes visuales complementarios:
1. Regla de tercios (posicionamiento en puntos y líneas áureas).
2. Armonía cromática (hasler-süsstrunk + saturación perceptual).
3. Rango dinámico (desviación RMS + riqueza tonal de histograma).
4. Aislamiento de sujeto (contraste perceptual centro/ROI vs periferia).
5. Calidad de iluminación (suavidad tonal y ausencia de fogonazos duros).
6. Balance compositivo (equilibrio del centro de masa visual).
7. Líneas guía / perspectiva (coherencia direccional de gradientes).
"""
import logging
from dataclasses import dataclass, asdict
import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AestheticBreakdown:
    rule_of_thirds: float      # [0.0 - 1.0]
    color_harmony: float       # [0.0 - 1.0]
    dynamic_range: float       # [0.0 - 1.0]
    subject_isolation: float   # [0.0 - 1.0]
    lighting_quality: float    # [0.0 - 1.0]
    composition_balance: float # [0.0 - 1.0]
    leading_lines: float       # [0.0 - 1.0]
    overall_score: float       # [0.0 - 1.0]

    def to_dict(self) -> dict:
        return asdict(self)


def compute_colorfulness(img_rgb: np.ndarray) -> float:
    """
    Calcula el "Colorfulness" según Hasler y Süsstrunk (2003).
    Mide cuán vivos y variados son los colores en la imagen.
    """
    if img_rgb.size == 0:
        return 0.0
    (R, G, B) = cv2.split(img_rgb.astype("float"))

    rg = np.absolute(R - G)
    yb = np.absolute(0.5 * (R + G) - B)

    stdRoot = np.sqrt((np.std(rg) ** 2) + (np.std(yb) ** 2))
    meanRoot = np.sqrt((np.mean(rg) ** 2) + (np.mean(yb) ** 2))

    colorfulness = stdRoot + (0.3 * meanRoot)
    return float(colorfulness)


def compute_color_harmony_score(img_rgb: np.ndarray) -> float:
    """Evalúa la armonía y viveza cromática normalizada [0.0 - 1.0]."""
    if img_rgb.size == 0:
        return 0.5
    c_score = compute_colorfulness(img_rgb)
    c_norm = min(1.0, c_score / 75.0)

    # Evaluar saturación en HSV
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    sat_mean = np.mean(sat) / 255.0
    # Premiar saturación moderada/viva (0.2 a 0.7), penalizar totalmente lavada o sobre-saturada
    sat_score = 1.0 - abs(sat_mean - 0.45) * 1.5
    sat_score = float(np.clip(sat_score, 0.0, 1.0))

    return float(np.clip(0.6 * c_norm + 0.4 * sat_score, 0.0, 1.0))


def compute_contrast(img_gray: np.ndarray) -> float:
    """Calcula el contraste dinámico usando la desviación estándar RMS."""
    if img_gray.size == 0:
        return 0.0
    return float(np.std(img_gray))


def compute_rule_of_thirds_score(img_gray: np.ndarray) -> float:
    """
    Evalúa si las áreas de saliencia/contraste caen en los puntos fuertes
    y líneas de la regla de los tercios.
    """
    h, w = img_gray.shape
    if h < 3 or w < 3:
        return 0.5

    grad_x = cv2.Sobel(img_gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(img_gray, cv2.CV_32F, 0, 1, ksize=3)
    saliency = cv2.magnitude(grad_x, grad_y)

    weight_mask = np.ones((h, w), dtype=np.float32) * 0.4

    # Coordenadas de los tercios
    x1, x2 = w // 3, 2 * w // 3
    y1, y2 = h // 3, 2 * h // 3

    # Líneas de tercios
    lw = max(1, int(min(h, w) * 0.04))
    weight_mask[max(0, y1 - lw):min(h, y1 + lw), :] = 0.7
    weight_mask[max(0, y2 - lw):min(h, y2 + lw), :] = 0.7
    weight_mask[:, max(0, x1 - lw):min(w, x1 + lw)] = 0.7
    weight_mask[:, max(0, x2 - lw):min(w, x2 + lw)] = 0.7

    # Intersecciones áureas
    r = int(min(h, w) * 0.15)
    for cx, cy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
        cv2.circle(weight_mask, (cx, cy), r, 1.0, -1)

    total_saliency = np.sum(saliency)
    if total_saliency == 0:
        return 0.5

    weighted_saliency = np.sum(saliency * weight_mask)
    score = weighted_saliency / total_saliency
    return float(np.clip((score - 0.4) * 2.0, 0.0, 1.0))


def compute_dynamic_range_score(img_gray: np.ndarray) -> float:
    """Evalúa la riqueza tonal y distribución del rango dinámico [0.0 - 1.0]."""
    if img_gray.size == 0:
        return 0.5
    h, w = img_gray.shape
    total_px = h * w
    if total_px == 0:
        return 0.5

    # Entropía del histograma
    hist = cv2.calcHist([img_gray], [0], None, [256], [0, 256]).flatten()
    hist_norm = hist / (total_px + 1e-8)
    entropy = -np.sum(hist_norm[hist_norm > 0] * np.log2(hist_norm[hist_norm > 0]))
    entropy_norm = min(1.0, entropy / 7.5)

    # RMS contrast
    rms = np.std(img_gray)
    rms_norm = min(1.0, rms / 55.0)

    # Penalización por clipping excesivo (>10% quemado o empastado)
    clipping_pct = (np.sum(img_gray >= 253) + np.sum(img_gray <= 2)) / total_px
    clip_penalty = max(0.0, (clipping_pct - 0.10) * 1.5)

    score = 0.5 * entropy_norm + 0.5 * rms_norm - clip_penalty
    return float(np.clip(score, 0.0, 1.0))


def compute_subject_isolation_score(img_gray: np.ndarray) -> float:
    """
    Evalúa el contraste y diferenciación perceptual entre el sujeto central/saliencia
    y el entorno periférico (aislamiento visual, complementario a nitidez).
    """
    h, w = img_gray.shape
    if h < 8 or w < 8:
        return 0.5

    # Región central (sujeto) vs bordes periféricos
    y1, y2 = h // 4, 3 * h // 4
    x1, x2 = w // 4, 3 * w // 4
    center_roi = img_gray[y1:y2, x1:x2]

    border_mask = np.ones((h, w), dtype=bool)
    border_mask[y1:y2, x1:x2] = False
    border_pixels = img_gray[border_mask]

    if center_roi.size == 0 or border_pixels.size == 0:
        return 0.5

    mean_diff = abs(float(np.mean(center_roi)) - float(np.mean(border_pixels)))
    std_diff = abs(float(np.std(center_roi)) - float(np.std(border_pixels)))

    # Mayor contraste tonal o de textura entre sujeto y fondo indica buen aislamiento
    isolation = (mean_diff / 40.0) * 0.6 + (std_diff / 30.0) * 0.4
    return float(np.clip(isolation, 0.0, 1.0))


def compute_lighting_quality_score(img_gray: np.ndarray) -> float:
    """
    Evalúa la suavidad y calidad de iluminación, penalizando fogonazos duros
    y sombras desbalanceadas en exceso.
    """
    h, w = img_gray.shape
    if h < 8 or w < 8:
        return 0.5

    # Dividir en rejilla 4x4 y medir coherencia de luminancia media
    gh, gw = 4, 4
    block_means = []
    for i in range(gh):
        for j in range(gw):
            blk = img_gray[i * h // gh:(i + 1) * h // gh, j * w // gw:(j + 1) * w // gw]
            if blk.size:
                block_means.append(float(np.mean(blk)))

    if not block_means:
        return 0.5

    light_var = np.std(block_means)
    # Variabilidad óptima: entre 15 y 45 (iluminación con volumen). Variabilidad > 75 = sombras/fogonazos duros
    if light_var <= 40:
        score = min(1.0, light_var / 25.0 + 0.3)
    else:
        score = max(0.0, 1.0 - (light_var - 40) / 45.0)

    return float(np.clip(score, 0.0, 1.0))


def compute_composition_balance_score(img_gray: np.ndarray) -> float:
    """
    Evalúa el equilibrio del centro de masa visual en el eje horizontal y vertical.
    """
    h, w = img_gray.shape
    if h < 3 or w < 3:
        return 0.5

    total_mass = float(np.sum(img_gray)) + 1e-6
    y_idx, x_idx = np.indices((h, w))
    cx = float(np.sum(x_idx * img_gray)) / total_mass
    cy = float(np.sum(y_idx * img_gray)) / total_mass

    # Desviación horizontal del centro
    dev_x = abs(cx - (w / 2.0)) / (w / 2.0)
    dev_y = abs(cy - (h / 2.0)) / (h / 2.0)

    # Puntuación de balance (1.0 = masa perfectamente centrada o equilibrada)
    balance = 1.0 - (0.65 * dev_x + 0.35 * dev_y)
    return float(np.clip(balance, 0.0, 1.0))


def compute_leading_lines_score(img_gray: np.ndarray) -> float:
    """
    Evalúa la presencia y coherencia de líneas guía y perspectiva dominante.
    """
    h, w = img_gray.shape
    if h < 8 or w < 8:
        return 0.5

    gx = cv2.Sobel(img_gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img_gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    if np.sum(mag) < 1e-5:
        return 0.5

    angles = np.arctan2(gy, gx)
    hist_angles, _ = np.histogram(angles, bins=16, range=(-np.pi, np.pi), weights=mag)
    total_w = float(np.sum(hist_angles)) + 1e-8
    hist_norm = hist_angles / total_w

    # Entropía angular: menor entropía = orientaciones dominantes (líneas guía claras)
    ent = -np.sum(hist_norm[hist_norm > 0] * np.log2(hist_norm[hist_norm > 0]))
    # 16 bins: max entropía es 4.0 (ruido isotrópico). Líneas claras tienen entropía < 3.2
    score = 1.0 - (ent / 4.0)
    return float(np.clip(score * 1.6, 0.0, 1.0))


def evaluate_aesthetics_detailed(img_rgb: np.ndarray) -> AestheticBreakdown:
    """
    Calcula el desglose completo de los 7 ejes estéticos.
    """
    if img_rgb.size == 0:
        return AestheticBreakdown(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)

    # Reducir imagen para procesamiento ultrarrápido (<5ms)
    h, w = img_rgb.shape[:2]
    max_dim = 256
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_small = cv2.resize(img_rgb, (int(w * scale), int(h * scale)))
    else:
        img_small = img_rgb

    img_gray = cv2.cvtColor(img_small, cv2.COLOR_RGB2GRAY)

    rot = compute_rule_of_thirds_score(img_gray)
    color = compute_color_harmony_score(img_small)
    dr = compute_dynamic_range_score(img_gray)
    iso = compute_subject_isolation_score(img_gray)
    light = compute_lighting_quality_score(img_gray)
    bal = compute_composition_balance_score(img_gray)
    lines = compute_leading_lines_score(img_gray)

    overall = (
        0.20 * rot +
        0.15 * color +
        0.15 * dr +
        0.15 * iso +
        0.15 * light +
        0.10 * bal +
        0.10 * lines
    )
    overall = float(np.clip(overall, 0.0, 1.0))

    return AestheticBreakdown(
        rule_of_thirds=round(rot, 4),
        color_harmony=round(color, 4),
        dynamic_range=round(dr, 4),
        subject_isolation=round(iso, 4),
        lighting_quality=round(light, 4),
        composition_balance=round(bal, 4),
        leading_lines=round(lines, 4),
        overall_score=round(overall, 4),
    )


def evaluate_aesthetics_fast(img_rgb: np.ndarray, return_features: bool = False) -> float | tuple[float, float, float]:
    """
    Calcula un score estético global [0.0 - 1.0] combinando los 7 ejes.
    Mantiene compatibilidad con versiones previas si return_features=True.
    """
    if img_rgb.size == 0:
        return (0.0, 0.0, 0.5) if return_features else 0.5

    bd = evaluate_aesthetics_detailed(img_rgb)

    if return_features:
        return (float(bd.color_harmony), float(bd.dynamic_range), float(bd.rule_of_thirds))
    return float(bd.overall_score)

