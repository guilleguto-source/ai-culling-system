"""
technical_quality.py — Análisis técnico de nitidez y exposición.
- Retratos: evalúa en el recorte del rostro para respetar el bokeh artístico.
- Objetos/Detalles: evalúa en la región de saliencia (zona de enfoque).
"""
import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TechnicalQualityResult:
    is_blurry: bool
    blur_score: float          # Varianza Laplaciana (mayor = más nítido)
    blur_region: str           # "face" | "saliency" | "full"
    is_overexposed: bool
    is_underexposed: bool
    overexposed_pct: float     # % de píxeles quemados (255)
    underexposed_pct: float    # % de píxeles empastados (0)
    dynamic_range_score: float # 0-1, mayor = mejor rango dinámico


# --- Nitidez ---

def _laplacian_variance(gray: np.ndarray) -> float:
    """Calcula la varianza del Laplaciano de una región en escala de grises."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def max_region_sharpness(img_rgb: np.ndarray, grid: int = 5) -> float:
    """
    Nitidez del bloque MÁS nítido de la imagen (rejilla grid x grid).
    Distingue el enfoque selectivo (rostros suaves pero ramo/manos nítidos →
    hay un bloque con alta varianza) del verdadero error de toma (nada nítido
    en ningún bloque: movida, disparo accidental).
    """
    if img_rgb is None or img_rgb.size == 0:
        return 0.0
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    h, w = lap.shape
    best = 0.0
    for i in range(grid):
        for j in range(grid):
            block = lap[i * h // grid:(i + 1) * h // grid,
                        j * w // grid:(j + 1) * w // grid]
            if block.size:
                best = max(best, float(block.var()))
    return best


def analyze_sharpness(
    img_rgb: np.ndarray,
    region_bbox: tuple[int, int, int, int] | None,
    region_label: str = "full",
) -> tuple[float, str]:
    """
    Calcula la nitidez en una región específica de la imagen.

    Args:
        img_rgb: Imagen completa en RGB.
        region_bbox: (x, y, w, h) de la región a evaluar, o None para imagen completa.
        region_label: Etiqueta descriptiva de la región ("face", "saliency", "full").

    Returns:
        (blur_score, region_label)
    """
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    if region_bbox is not None:
        x, y, w, h = region_bbox
        # Asegurar que el recorte esté dentro de los límites
        x, y = max(0, x), max(0, y)
        x2 = min(img_rgb.shape[1], x + w)
        y2 = min(img_rgb.shape[0], y + h)
        region = gray[y:y2, x:x2]
        if region.size == 0:
            region = gray
            region_label = "full"
    else:
        region = gray

    score = _laplacian_variance(region)
    return score, region_label


def evaluate_blur(
    img_rgb: np.ndarray,
    scene_type: str,                            # "portrait" | "detail"
    face_bboxes: list[list[int]],
    saliency_region: tuple[int, int, int, int] | None,
    blur_threshold: float,
) -> tuple[bool, float, str]:
    """
    Determina si la imagen es borrosa, adaptándose al tipo de escena.

    - portrait: mide nitidez en el primer rostro detectado.
    - detail: mide nitidez en la región de saliencia.

    Returns:
        (is_blurry, blur_score, region_label)
    """
    if scene_type == "portrait" and face_bboxes:
        # Ampliar ligeramente el bbox del rostro para incluir ojos y frente
        x, y, w, h = face_bboxes[0]
        region = (x, y, w, h)
        score, label = analyze_sharpness(img_rgb, region, "face")
    elif scene_type == "detail" and saliency_region:
        score, label = analyze_sharpness(img_rgb, saliency_region, "saliency")
    else:
        score, label = analyze_sharpness(img_rgb, None, "full")

    is_blurry = score < blur_threshold
    if is_blurry:
        logger.debug(f"BORROSA — score={score:.1f} < umbral={blur_threshold} [{label}]")

    return is_blurry, score, label


# --- Exposición y Rango Dinámico ---

def analyze_exposure(
    img_rgb: np.ndarray,
    scene_type: str,
    face_bboxes: list[list[int]],
    saliency_region: tuple[int, int, int, int] | None,
    clipping_threshold_pct: float = 3.0,
) -> tuple[bool, bool, float, float, float]:
    """
    Analiza la exposición de la imagen.
    Prioriza el análisis sobre el sujeto principal (rostro o zona de saliencia).

    Returns:
        (is_overexposed, is_underexposed, overexposed_pct, underexposed_pct, dynamic_range_score)
    """
    # Seleccionar región de análisis
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    if scene_type == "portrait" and face_bboxes:
        x, y, w, h = face_bboxes[0]
        x, y = max(0, x), max(0, y)
        region = gray[y:min(gray.shape[0], y + h), x:min(gray.shape[1], x + w)]
        if region.size == 0:
            region = gray
    elif scene_type == "detail" and saliency_region:
        rx, ry, rw, rh = saliency_region
        region = gray[ry:ry + rh, rx:rx + rw]
    else:
        region = gray

    total_pixels = region.size
    if total_pixels == 0:
        return False, False, 0.0, 0.0, 0.5

    # Calcular porcentajes de píxeles en extremos
    overexposed_pct = float(np.sum(region >= 253) / total_pixels * 100)
    underexposed_pct = float(np.sum(region <= 2) / total_pixels * 100)

    is_overexposed = overexposed_pct > clipping_threshold_pct
    is_underexposed = underexposed_pct > clipping_threshold_pct

    # Score de rango dinámico: qué tan bien distribuido está el histograma
    hist = cv2.calcHist([region], [0], None, [256], [0, 256]).flatten()
    hist_norm = hist / (total_pixels + 1e-8)
    # Entropía del histograma como proxy del rango dinámico (0-1)
    entropy = -np.sum(hist_norm[hist_norm > 0] * np.log2(hist_norm[hist_norm > 0]))
    dynamic_range_score = min(1.0, entropy / 8.0)  # 8 bits = entropía máxima teórica

    return is_overexposed, is_underexposed, overexposed_pct, underexposed_pct, dynamic_range_score


def evaluate_technical_quality(
    img_rgb: np.ndarray,
    scene_type: str,
    face_bboxes: list[list[int]],
    saliency_region: tuple[int, int, int, int] | None,
    blur_threshold: float,
) -> TechnicalQualityResult:
    """
    Evaluación técnica completa: nitidez + exposición.
    """
    is_blurry, blur_score, blur_region = evaluate_blur(
        img_rgb, scene_type, face_bboxes, saliency_region, blur_threshold
    )
    is_overexposed, is_underexposed, over_pct, under_pct, dr_score = analyze_exposure(
        img_rgb, scene_type, face_bboxes, saliency_region
    )

    return TechnicalQualityResult(
        is_blurry=is_blurry,
        blur_score=blur_score,
        blur_region=blur_region,
        is_overexposed=is_overexposed,
        is_underexposed=is_underexposed,
        overexposed_pct=over_pct,
        underexposed_pct=under_pct,
        dynamic_range_score=dr_score,
    )
