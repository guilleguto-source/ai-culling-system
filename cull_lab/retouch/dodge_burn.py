"""
CullLab Neutral Gray Dodge & Burn Engine
Inspirado en los módulos NeutralGray, NeutralGrayBodyEven y NeutralGrayHand de Evoto AI.
Permite esculpir volumen, atenuar ojeras y surcos mediante fusión Soft Light sin alterar la saturación cromática.
"""

from __future__ import annotations

from typing import Optional
import cv2
import numpy as np


class NeutralGrayDodgeBurn:
    """
    Motor de Dodge & Burn digital operando sobre capas de gris neutro al 50%.
    """

    @staticmethod
    def create_neutral_layer(shape: tuple) -> np.ndarray:
        """Crea una capa plana inicializada en 0.5f (50% gris neutro, estado de reposo)."""
        return np.full(shape, 0.5, dtype=np.float32)

    @staticmethod
    def _normalize_input(image: np.ndarray) -> np.ndarray:
        """Normaliza de forma segura imágenes uint8 [0, 255] o float [0.0, 1.0]."""
        if image.dtype == np.uint8:
            return image.astype(np.float32) / 255.0
        if np.issubdtype(image.dtype, np.floating) and image.size > 0 and np.nanmax(image) > 1.0:
            return np.clip(image.astype(np.float32) / 255.0, 0.0, 1.0)
        return np.clip(image.astype(np.float32), 0.0, 1.0)

    @classmethod
    def blend_soft_light(
        cls,
        base_image: np.ndarray,
        gray_layer: np.ndarray,
        opacity: float = 1.0,
    ) -> np.ndarray:
        """
        Fusión de gris neutro sobre imagen base según el estándar W3C/Photoshop de Soft Light.
        - gray_layer = 0.5f  -> Identidad exacta (sin cambios).
        - gray_layer > 0.5f  -> Dodge (aclara sombras de forma suave).
        - gray_layer < 0.5f  -> Burn (oscurece luces sin quemar).
        """
        b = cls._normalize_input(base_image)
        s = cls._normalize_input(gray_layer)

        # Si gray_layer tiene un solo canal y base_image es 3 canales
        if s.ndim == 2 and b.ndim == 3:
            s = np.expand_dims(s, axis=-1)
        elif s.ndim == 3 and b.ndim == 3 and s.shape[-1] == 1:
            s = np.repeat(s, b.shape[-1], axis=-1)

        # Función auxiliar D(B) para B > 0.25 y B <= 0.25
        d_b = np.where(b <= 0.25, ((16.0 * b - 12.0) * b + 4.0) * b, np.sqrt(np.maximum(1e-8, b)))

        # Fórmula W3C Soft Light
        blended = np.where(
            s <= 0.5,
            b - (1.0 - 2.0 * s) * b * (1.0 - b),
            b + (2.0 * s - 1.0) * (d_b - b),
        )

        # Modulación por opacidad
        if opacity < 1.0:
            blended = (1.0 - opacity) * b + opacity * blended

        return np.clip(blended, 0.0, 1.0)

    @classmethod
    def auto_even_skin_tones(
        cls,
        image: np.ndarray,
        skin_mask: Optional[np.ndarray] = None,
        strength: float = 0.40,
        dark_circle_lift: float = 0.15,
    ) -> np.ndarray:
        """
        Calcula automáticamente una capa de Dodge & Burn para homogeneizar
        la iluminación de la piel, aclarando sombras duras sin desaturar.
        """
        img_f32 = cls._normalize_input(image)
        gray_layer = cls.create_neutral_layer(img_f32.shape[:2])

        # Calcular canal de luminancia (sRGB ITU-R BT.709)
        if img_f32.ndim == 3:
            luma = 0.2126 * img_f32[..., 0] + 0.7152 * img_f32[..., 1] + 0.0722 * img_f32[..., 2]
        else:
            luma = img_f32.copy()

        # Mediana/media local de luminancia
        blurred_luma = cv2.GaussianBlur(luma, (31, 31), 10.0)

        # Diferencia: áreas más oscuras que su entorno local reciben un "dodge" (+ valor)
        luma_diff = blurred_luma - luma
        dodge_mask = np.clip(luma_diff * dark_circle_lift, -0.25, 0.25)

        # Aplicar solo dentro de la máscara de piel si se proporciona
        if skin_mask is not None:
            mask = np.clip(skin_mask.astype(np.float32), 0.0, 1.0)
            if mask.ndim == 3:
                mask = mask[..., 0]
            dodge_mask = dodge_mask * mask

        # Construir capa de gris: 0.5 + dodge_mask
        gray_layer = np.clip(0.5 + dodge_mask, 0.0, 1.0)

        # Fusionar con opacidad controlada
        return cls.blend_soft_light(img_f32, gray_layer, opacity=strength)
