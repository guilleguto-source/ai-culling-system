"""
CullLab Smart Crop & Inscribed Composition Engine
Inspirado en los algoritmos de recorte circunscrito de Imagen AI y Camera Raw.
Calcula analíticamente el área máxima sin cuñas vacías y encuadra respetando sujetos y regla de tercios.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class SubjectBBox:
    """Caja delimitadora normalizada de un sujeto o rostro [0, 1]."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def center_x(self) -> float:
        return (self.xmin + self.xmax) / 2.0

    @property
    def center_y(self) -> float:
        return (self.ymin + self.ymax) / 2.0


@dataclass
class CropCoordinates:
    """Coordenadas de recorte normalizadas [0, 1] compatibles con crs:Crop* de Adobe."""
    top: float
    left: float
    bottom: float
    right: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def as_tuple(self) -> Tuple[float, float, float, float]:
        """Devuelve (top, left, bottom, right)."""
        return (round(self.top, 6), round(self.left, 6), round(self.bottom, 6), round(self.right, 6))


class SmartCropper:
    """
    Calculador analítico de recorte circunscrito y encuadre guiado por sujetos.
    """

    def __init__(self, target_aspect_ratio: Optional[float] = None):
        """
        target_aspect_ratio: Si es None, preserva el aspect ratio nativo de la imagen original.
        """
        self.target_aspect_ratio = target_aspect_ratio

    def compute_crop(
        self,
        image_width: int,
        image_height: int,
        tilt_angle_degrees: float = 0.0,
        subjects: Optional[Sequence[SubjectBBox]] = None,
        headroom_ratio: float = 0.04,  # Margen de seguridad sobre la cabeza (4% de la altura)
    ) -> CropCoordinates:
        """
        Calcula el recorte óptimo que elimina esquinas vacías producidas por la rotación
        y adapta el encuadre para no cortar sujetos respetando la regla de tercios.
        """
        w = float(image_width)
        h = float(image_height)
        native_aspect = w / h
        aspect = self.target_aspect_ratio if self.target_aspect_ratio is not None else native_aspect

        alpha = math.radians(abs(tilt_angle_degrees))

        # 1. Escala analítica máxima inscrita dentro del marco rotado
        if alpha < 1e-5:
            scale = 1.0
        else:
            # Fórmula analítica del rectángulo máximo inscrito manteniendo aspect ratio R = W/H
            # Para imágenes tanto horizontales como verticales (R < 1 o R >= 1):
            # scale = 1.0 / (max(R, 1/R) * sin(alpha) + cos(alpha))
            effective_ratio = max(native_aspect, 1.0 / native_aspect)
            denom = (effective_ratio * math.sin(alpha)) + math.cos(alpha)
            scale = 1.0 / max(1e-5, denom)

        # Dimensiones del recorte normalizadas respecto a la imagen original [0, 1]
        crop_w = min(1.0, max(0.1, scale))
        crop_h = min(1.0, max(0.1, crop_w * (native_aspect / aspect)))

        # 2. Centrado base
        center_x = 0.5
        center_y = 0.5

        # 3. Ajuste consciente de sujetos (si existen)
        if subjects:
            # Encontrar el bounding box colectivo de todos los sujetos
            min_x = min(s.xmin for s in subjects)
            max_x = max(s.xmax for s in subjects)
            min_y = min(s.ymin for s in subjects)
            max_y = max(s.ymax for s in subjects)

            subj_center_x = (min_x + max_x) / 2.0

            # Regla de tercios: en fotografía de retratos, los ojos/rostro deben
            # ubicarse cerca del tercio superior (y ≈ 0.33) dentro del recorte
            # center_y deseado = min_y - (crop_h * 0.15) + (crop_h / 2)
            desired_center_y = min_y + (crop_h * 0.35)
            desired_center_x = subj_center_x

            # Desplazar suavemente el centro hacia el sujeto sin salir del margen seguro
            center_x = desired_center_x
            center_y = desired_center_y

            # Regla de oro de encuadre: GARANTIZAR que no se corte la cabeza (headroom)
            # El top del crop debe estar por encima de min_y - headroom
            min_allowed_top = min_y - headroom_ratio
            if (center_y - crop_h / 2.0) > min_allowed_top:
                center_y = min_allowed_top + (crop_h / 2.0)

        # 4. Clampear el centro dentro de los límites válidos [crop/2, 1 - crop/2]
        half_w = crop_w / 2.0
        half_h = crop_h / 2.0

        clamped_cx = max(half_w, min(1.0 - half_w, center_x))
        clamped_cy = max(half_h, min(1.0 - half_h, center_y))

        # 5. Coordenadas finales [0, 1]
        top = clamped_cy - half_h
        bottom = clamped_cy + half_h
        left = clamped_cx - half_w
        right = clamped_cx + half_w

        return CropCoordinates(
            top=max(0.0, min(1.0, top)),
            left=max(0.0, min(1.0, left)),
            bottom=max(0.0, min(1.0, bottom)),
            right=max(0.0, min(1.0, right)),
        )
