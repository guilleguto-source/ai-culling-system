"""
tonal_rescue.py — Módulo de rescate tonal de altas luces y sombras (Fase 3).

Detecta fotos con pérdida de detalle en altas luces (>5% píxeles quemados) o
sombras profundas (>10% píxeles negros) y propone ajustes paramétricos crs
(Highlights2012, Shadows2012, Whites2012, Blacks2012) no destructivos.

Reglas:
- Solo actúa cuando supera los umbrales (Opción A).
- Fotos bien equilibradas no se tocan (dict vacío).
- Escalado sigmoidal suave para evitar saltos bruscos.
"""
from dataclasses import dataclass
import logging
from typing import Any
import numpy as np

logger = logging.getLogger(__name__)

# Umbrales de intervención por defecto (Opción A: solo ante problemas reales)
HIGHLIGHTS_CLIP_THRESHOLD = 0.05  # >5% de píxeles con luminancia >0.97
SHADOWS_CLIP_THRESHOLD = 0.10     # >10% de píxeles con luminancia <0.04

# Límites máximos de corrección paramétrica (escala Lightroom -100..100)
MAX_HIGHLIGHTS_CORRECTION = -80
MAX_SHADOWS_CORRECTION = 70


@dataclass
class TonalReport:
    highlights_clip: float  # fracción [0..1]
    shadows_clip: float     # fracción [0..1]
    midtone_lum: float      # luminancia lineal mediana [0..1]
    has_faces: bool         # si contiene personas


def _linear_luminance(img_rgb: np.ndarray) -> np.ndarray:
    """Luminancia lineal aproximada (gamma 2.2) 0..1."""
    norm = img_rgb.astype(np.float32) / 255.0
    lum = 0.2126 * norm[..., 0] + 0.7152 * norm[..., 1] + 0.0722 * norm[..., 2]
    return np.power(np.clip(lum, 1e-4, 1.0), 2.2)


def analyze_tonal_range(img_rgb: np.ndarray, face_bboxes: list[list[int]] | None = None) -> TonalReport:
    """Analiza la distribución tonal y fracción de corte en altas luces y sombras."""
    if img_rgb is None or img_rgb.size == 0:
        return TonalReport(highlights_clip=0.0, shadows_clip=0.0, midtone_lum=0.18, has_faces=False)

    lum = _linear_luminance(img_rgb)
    
    highlights_clip = float(np.mean(lum > 0.97))
    shadows_clip = float(np.mean(lum < 0.04))
    midtone_lum = float(np.median(lum))
    has_faces = bool(face_bboxes and len(face_bboxes) > 0)
    
    return TonalReport(
        highlights_clip=round(highlights_clip, 4),
        shadows_clip=round(shadows_clip, 4),
        midtone_lum=round(midtone_lum, 4),
        has_faces=has_faces,
    )


def _smooth_step(val: float, edge0: float, edge1: float) -> float:
    """Interpolación hermitiana suave (smoothstep) entre edge0 y edge1 normalizada en [0, 1]."""
    x = np.clip((val - edge0) / max(1e-6, edge1 - edge0), 0.0, 1.0)
    return float(x * x * (3.0 - 2.0 * x))


def suggest_tonal_adjustments(
    report: TonalReport,
    highlights_threshold: float = HIGHLIGHTS_CLIP_THRESHOLD,
    shadows_threshold: float = SHADOWS_CLIP_THRESHOLD,
) -> dict[str, int]:
    """
    Calcula los ajustes paramétricos crs sugeridos según el reporte tonal.
    Retorna {} si la foto está bien balanceada.
    """
    adjustments: dict[str, int] = {}
    
    # 1. Rescate de Altas Luces (Highlights & Whites)
    if report.highlights_clip > highlights_threshold:
        # Satura al llegar a 20% de quemado
        factor = _smooth_step(report.highlights_clip, highlights_threshold, 0.20)
        hi = int(round(MAX_HIGHLIGHTS_CORRECTION * factor))
        if hi != 0:
            adjustments["Highlights2012"] = hi
            # Whites compensa un 40% del ajuste de altas luces
            wh = int(round(hi * 0.4))
            if wh != 0:
                adjustments["Whites2012"] = wh
                
    # 2. Rescate de Sombras (Shadows & Blacks)
    if report.shadows_clip > shadows_threshold:
        # Satura al llegar a 35% de sombras profundas
        factor = _smooth_step(report.shadows_clip, shadows_threshold, 0.35)
        sh = int(round(MAX_SHADOWS_CORRECTION * factor))
        if sh != 0:
            adjustments["Shadows2012"] = sh
            # Blacks levanta un 30% del ajuste de sombras
            bl = int(round(sh * 0.3))
            if bl != 0:
                adjustments["Blacks2012"] = bl
                
    return adjustments


def batch_rescue(
    images_data: list[dict[str, Any]],
    highlights_threshold: float = HIGHLIGHTS_CLIP_THRESHOLD,
    shadows_threshold: float = SHADOWS_CLIP_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Procesa un lote de imágenes con sus reportes tonales y calcula los ajustes sugeridos.
    images_data: lista de dicts con {"path": str, "img_rgb": np.ndarray | None, "report": TonalReport | None}
    """
    results = []
    for item in images_data:
        report = item.get("report")
        if report is None and item.get("img_rgb") is not None:
            report = analyze_tonal_range(item["img_rgb"], item.get("face_bboxes"))
        
        adjustments = {}
        if report is not None:
            adjustments = suggest_tonal_adjustments(
                report,
                highlights_threshold=highlights_threshold,
                shadows_threshold=shadows_threshold,
            )
        
        results.append({
            "path": item.get("path", ""),
            "report": report,
            "adjustments": adjustments,
            "needs_rescue": bool(adjustments),
        })
    return results
