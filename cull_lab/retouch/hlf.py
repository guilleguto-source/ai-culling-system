"""
CullLab High-Low Frequency (HLF) Skin Separation & Retouching Engine
Inspirado en los módulos FaceDermabrasionHLF y BodyDermabrasionHLF de Evoto AI.
Separa gradientes tonales (baja frecuencia) de micro-poros (alta frecuencia) para suavizar sin aspecto plástico.
"""

from __future__ import annotations

from typing import Optional, Tuple
import cv2
import numpy as np


class HLFSeparation:
    """
    Separación y reconstrucción ortogonal de frecuencias para retoque dérmico natural.
    """

    @staticmethod
    def _normalize_input(image: np.ndarray) -> np.ndarray:
        """Normaliza de forma segura imágenes uint8 [0, 255] o float [0.0, 1.0]."""
        if image.dtype == np.uint8:
            return image.astype(np.float32) / 255.0
        if np.issubdtype(image.dtype, np.floating) and image.size > 0 and np.nanmax(image) > 1.0:
            return np.clip(image.astype(np.float32) / 255.0, 0.0, 1.0)
        return np.clip(image.astype(np.float32), 0.0, 1.0)

    @classmethod
    def decompose(
        cls,
        image: np.ndarray,
        radius: int = 7,
        sigma_color: float = 0.15,
        sigma_space: float = 7.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Descompone una imagen RGB (uint8 o float32) en:
        - low_freq: Gradientes de tono continuo y color (sin detalles microscópicos).
        - high_freq: Textura de poros, vello fino y microcontraste (diferencia con signo).
        """
        img_f32 = cls._normalize_input(image)

        # Filtro bilateral para preservar bordes anatómicos en la capa de baja frecuencia
        d = radius * 2 + 1
        low_freq = cv2.bilateralFilter(img_f32, d=d, sigmaColor=sigma_color, sigmaSpace=sigma_space)

        # La capa de alta frecuencia es la diferencia exacta con signo
        high_freq = img_f32 - low_freq

        return low_freq, high_freq

    @staticmethod
    def reconstruct(low_freq: np.ndarray, high_freq: np.ndarray) -> np.ndarray:
        """Reconstruye la imagen sumando las dos bandas de frecuencia ortogonales."""
        return np.clip(low_freq + high_freq, 0.0, 1.0)

    @classmethod
    def smooth_skin(
        cls,
        image: np.ndarray,
        skin_mask: Optional[np.ndarray] = None,
        smooth_strength: float = 0.5,      # Intensidad de suavizado dérmico [0, 1]
        texture_preservation: float = 1.0, # Nivel de textura natural a conservar (1.0 = 100%)
        radius: int = 9,
    ) -> np.ndarray:
        """
        Aplica suavizado adaptativo sobre las bajas frecuencias dentro de la máscara de piel,
        reintegrando la capa de alta frecuencia (poros) intacta.
        """
        img_f32 = cls._normalize_input(image)

        if smooth_strength <= 0.0:
            return img_f32

        # 1. Descomposición inicial
        low_freq, high_freq = cls.decompose(img_f32, radius=radius)

        # 2. Suavizado tonal secundario de mayor radio sobre la capa baja
        smooth_low = cv2.bilateralFilter(
            low_freq,
            d=radius * 2 + 1,
            sigmaColor=0.25,
            sigmaSpace=radius * 1.5,
        )

        # 3. Modular por la máscara de piel (o máscara uniforme si no se proporciona)
        if skin_mask is not None:
            mask = np.clip(skin_mask.astype(np.float32), 0.0, 1.0)
            if mask.ndim == 2 and img_f32.ndim == 3:
                mask = np.expand_dims(mask, axis=-1)
        else:
            mask = np.ones_like(img_f32[..., :1] if img_f32.ndim == 3 else img_f32)

        effective_weight = mask * smooth_strength
        blended_low = (1.0 - effective_weight) * low_freq + effective_weight * smooth_low

        # 4. Modulación de textura de alta frecuencia
        effective_high = high_freq * texture_preservation

        # 5. Reconstrucción final con poros preservados
        return cls.reconstruct(blended_low, effective_high)
