"""
CullLab Blur & Bokeh Discriminator
Inspirado en el desacoplamiento blur_salient vs blur_background de Topaz Photo AI.
Distingue el bokeh intencional por apertura amplia (f/1.2 - f/2.8) de la trepidación o foco perdido.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class BlurAnalysisResult:
    """Diagnóstico detallado de nitidez espectral y óptica."""
    subject_sharpness: float            # 0 (completamente borroso) a 10 (perfecto)
    background_sharpness: float         # 0 a 10
    directional_coherence: float        # 0 (isotrópico/lente) a 1 (unidireccional/trepidación)
    is_bokeh_intentional: bool          # Fondo desenfocado intencionalmente (retrato f/1.4)
    is_motion_blur: bool                # Trepidación o movimiento del sujeto
    is_missed_focus: bool               # Foco perdido (sujeto borroso sin trepidación)
    is_acceptable_for_cull: bool        # Veredicto para culling automático
    recommended_sharpen_scope: str      # 'Subject', 'All', 'None'


class BlurAnalyzer:
    """
    Analizador diferencial de nitidez de sujeto vs fondo.
    Evita falsos rechazos en retratos con aperturas luminosas.
    """

    def __init__(
        self,
        sharpness_threshold: float = 4.5,   # Umbral mínimo de sujeto aceptable
        bokeh_ratio_threshold: float = 1.8, # background_blur / subject_blur mínimo para bokeh
        motion_coherence_threshold: float = 0.60, # Coherencia angular mínima para trepidación
    ):
        self.thresh = sharpness_threshold
        self.bokeh_ratio = bokeh_ratio_threshold
        self.motion_coherence_thresh = motion_coherence_threshold

    def analyze_blur(
        self,
        subject_laplacian_var: float,      # Varianza Laplaciana en sujeto (> 500 = nítido)
        background_laplacian_var: float,   # Varianza Laplaciana en fondo
        gradient_angle_dispersion: float,  # Dispersión circular [0, 1] (0 = todos los bordes paralelos)
    ) -> BlurAnalysisResult:
        """
        Analiza las energías de alta frecuencia en sujeto y fondo.
        Calcula el veredicto óptico.
        """
        # Normalizar varianza Laplaciana a escala perceptiva 0 a 10
        # (Logarítmica: 100 -> ~3.0, 500 -> ~6.0, 2000 -> ~9.0)
        s_score = self._laplacian_to_score(subject_laplacian_var)
        bg_score = self._laplacian_to_score(background_laplacian_var)

        # Coherencia direccional: 1.0 - dispersión angular
        # Si dispersión es baja (< 0.40), la coherencia direccional es alta (> 0.60) -> trepidación
        directional_coherence = max(0.0, min(1.0, 1.0 - gradient_angle_dispersion))

        # 1. Detección de Bokeh Intencional:
        # Sujeto nítido Y fondo significativamente más borroso que el sujeto
        is_bokeh = (s_score >= self.thresh) and (s_score >= bg_score * self.bokeh_ratio)

        # 2. Diagnóstico de Falla si el sujeto está borroso:
        is_motion = False
        is_missed = False

        if s_score < self.thresh:
            if directional_coherence >= self.motion_coherence_thresh:
                is_motion = True  # Trepidación (movimiento direccional)
            else:
                is_missed = True  # Foco errado / lente blanda (desenfoque radial isotrópico)

        # 3. Veredicto de Culling
        is_acceptable = (s_score >= self.thresh)

        # 4. Alcance de Enfoque Recomendado
        if is_bokeh:
            sharpen_scope = "Subject"  # NUNCA enfocar el fondo bokeh
        elif is_acceptable:
            sharpen_scope = "All"
        else:
            sharpen_scope = "None"     # Rechazada para culling

        return BlurAnalysisResult(
            subject_sharpness=round(s_score, 2),
            background_sharpness=round(bg_score, 2),
            directional_coherence=round(directional_coherence, 2),
            is_bokeh_intentional=is_bokeh,
            is_motion_blur=is_motion,
            is_missed_focus=is_missed,
            is_acceptable_for_cull=is_acceptable,
            recommended_sharpen_scope=sharpen_scope,
        )

    @staticmethod
    def _laplacian_to_score(var: float) -> float:
        """Transforma la varianza Laplaciana (0 a 3000+) en una escala visual de 0 a 10."""
        if var <= 5.0:
            return 0.5
        # Transformación logarítmica suavizada
        val = (math.log10(max(10.0, var)) - 1.0) / (math.log10(2500.0) - 1.0) * 10.0
        return max(0.0, min(10.0, val))
