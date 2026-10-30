"""
CullLab Auto-Straighten & Tilt Estimator
Inspirado en los algoritmos de detección de horizonte geométrico de Imagen AI y Lightroom.
Calcula el ángulo de inclinación θ mediante regresión robusta (RANSAC / mediana ponderada) sobre líneas de fuga.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class LineSegment:
    """Segmento de línea en coordenadas de imagen (x1, y1, x2, y2)."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle_degrees(self) -> float:
        """Ángulo en grados en el rango [-180, 180]."""
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))


@dataclass
class StraightenResult:
    """Resultado del análisis de inclinación de la escena."""
    tilt_angle_degrees: float           # Ángulo θ a rotar (-15° a +15°)
    confidence: float                   # Confianza [0, 1] basada en longitud y consistencia
    horizontal_lines_count: int         # Número de líneas de soporte horizontal
    vertical_lines_count: int           # Número de líneas de soporte vertical
    needs_straighten: bool              # True si |θ| >= umbral de histéresis


class StraightenDetector:
    """
    Detector de inclinación angular basado en regularidades geométricas (horizontes y verticales).
    """

    def __init__(
        self,
        max_tilt_search_degrees: float = 15.0,  # Búsqueda angular máxima (±15°)
        deadband_threshold_degrees: float = 0.20, # Inclinaciones menores a 0.2° se ignoran
        min_segment_length: float = 20.0,        # Descartar micro-texturas
    ):
        self.max_tilt = max_tilt_search_degrees
        self.deadband = deadband_threshold_degrees
        self.min_length = min_segment_length

    def estimate_tilt_from_segments(self, segments: Sequence[LineSegment]) -> StraightenResult:
        """
        Calcula el ángulo θ óptimo a partir de un conjunto de segmentos de línea detectados.
        """
        valid_segments = [s for s in segments if s.length >= self.min_length]
        if not valid_segments:
            return StraightenResult(
                tilt_angle_degrees=0.0,
                confidence=0.0,
                horizontal_lines_count=0,
                vertical_lines_count=0,
                needs_straighten=False,
            )

        horizontal_angles: List[Tuple[float, float]] = [] # (angle, weight)
        vertical_angles: List[Tuple[float, float]] = []

        for seg in valid_segments:
            ang = seg.angle_degrees
            weight = seg.length

            # Normalizar a [-90, 90]
            if ang > 90.0:
                ang -= 180.0
            elif ang < -90.0:
                ang += 180.0

            # 1. Candidato a línea horizontal (cerca de 0°)
            if abs(ang) <= self.max_tilt:
                horizontal_angles.append((ang, weight))

            # 2. Candidato a línea vertical (cerca de ±90°)
            elif abs(abs(ang) - 90.0) <= self.max_tilt:
                # Desviación respecto a la vertical estricta
                vert_dev = ang - 90.0 if ang > 0 else ang + 90.0
                vertical_angles.append((vert_dev, weight))

        total_candidates = horizontal_angles + vertical_angles
        if not total_candidates:
            return StraightenResult(
                tilt_angle_degrees=0.0,
                confidence=0.0,
                horizontal_lines_count=0,
                vertical_lines_count=0,
                needs_straighten=False,
            )

        # Regresión robusta: Mediana ponderada con rechazo de outliers (RANSAC simplificado)
        best_angle = self._weighted_median_ransac(total_candidates)

        # Histéresis de banda muerta
        needs_straighten = abs(best_angle) >= self.deadband
        final_angle = round(best_angle, 4) if needs_straighten else 0.0

        # Confianza basada en longitud acumulada de soporte
        support_length = sum(w for a, w in total_candidates if abs(a - best_angle) <= 1.0)
        total_length = sum(w for a, w in total_candidates)
        confidence = min(1.0, (support_length / max(1.0, total_length)) * min(1.0, support_length / 200.0))

        return StraightenResult(
            tilt_angle_degrees=final_angle,
            confidence=round(confidence, 3),
            horizontal_lines_count=len(horizontal_angles),
            vertical_lines_count=len(vertical_angles),
            needs_straighten=needs_straighten,
        )

    def _weighted_median_ransac(self, candidates: List[Tuple[float, float]]) -> float:
        """Calcula el ángulo dominante mediante consenso ponderado y rechazo de dispersión."""
        if len(candidates) == 1:
            return candidates[0][0]

        # Ordenar candidatos por ángulo
        sorted_cand = sorted(candidates, key=lambda x: x[0])
        total_weight = sum(w for _, w in sorted_cand)
        half_weight = total_weight / 2.0

        # Encontrar mediana ponderada
        cum_weight = 0.0
        median_angle = sorted_cand[0][0]
        for a, w in sorted_cand:
            cum_weight += w
            if cum_weight >= half_weight:
                median_angle = a
                break

        # Refinamiento RANSAC: promediar únicamente los inliers dentro de ±1.5° de la mediana
        inlier_sum = 0.0
        inlier_weight = 0.0
        for a, w in sorted_cand:
            if abs(a - median_angle) <= 1.5:
                inlier_sum += a * w
                inlier_weight += w

        if inlier_weight > 0.0:
            return inlier_sum / inlier_weight
        return median_angle
