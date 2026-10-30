"""
tonal_engine.py — Motor analítico de revelado fotográfico y aplicación de presets.
Aplica sobre píxeles:
1. Compensación de exposición lineal (2^EV) calculada por pre_edit.py.
2. Balance de blancos incremental (Temp/Tint).
3. Receta tonal GutoPro Day Boy (levantamiento de sombras +30, protección de altas luces -10,
   tonos negros ricos, curva tonal y calidez de piel).
"""

from __future__ import annotations

import math
import numpy as np
import cv2
from typing import Optional, Tuple


class TonalEngine:
    """
    Simulador fiel y eficiente del pipeline de revelado de Adobe Camera Raw / Lightroom.
    """

    @staticmethod
    def develop_photo(
        img_rgb: np.ndarray,
        exposure_ev: float = 0.0,
        temp_inc: float = 10.0,        # +10 por GutoPro Day Boy
        tint_inc: float = 6.0,          # +6 por GutoPro Day Boy
        highlights: float = -10.0,      # Highlights2012 = -10
        shadows: float = +30.0,         # Shadows2012 = +30
        whites: float = -14.0,          # Whites2012 = -14
        blacks: float = -11.0,          # Blacks2012 = -11
        contrast: float = -10.0,        # Contrast2012 = -10
        vibrance: float = +3.0,         # Vibrance = +3
        saturation: float = -2.0,       # Saturation = -2
    ) -> np.ndarray:
        """
        Aplica la cadena de revelado completa sobre la imagen sRGB en memoria.
        """
        if img_rgb is None or img_rgb.size == 0:
            return img_rgb

        # 1. Normalización y linealización (espacio de trabajo lineal)
        img_f = img_rgb.astype(np.float32) / 255.0
        # Des-gamma aproximado
        lin = np.power(np.clip(img_f, 1e-5, 1.0), 2.2)

        # 2. Compensación de exposición lineal (2^EV)
        if abs(exposure_ev) > 0.01:
            gain = math.pow(2.0, float(np.clip(exposure_ev, -2.5, 3.0)))
            lin *= gain

        # 3. Balance de blancos adaptativo (Temp / Tint)
        # Temp: +10 hace la foto más cálida (+R, -B)
        r_gain = 1.0 + (temp_inc * 0.008)
        b_gain = 1.0 - (temp_inc * 0.008)
        # Tint: +6 agrega leve magenta (+R, +B, -G)
        g_gain = 1.0 - (tint_inc * 0.006)

        lin[..., 0] *= r_gain
        lin[..., 1] *= g_gain
        lin[..., 2] *= b_gain

        # 4. Compresión de altas luces y levantamiento de sombras en espacio lineal
        # Luminancia perceptual
        lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
        lum = np.maximum(lum, 1e-6)

        # Máscaras de sombras (lum < 0.25) y altas luces (lum > 0.5)
        shadow_mask = np.clip(1.0 - (lum / 0.35), 0.0, 1.0)
        highlight_mask = np.clip((lum - 0.40) / 0.60, 0.0, 1.0)

        # Shadows lift (+30 en LR equivale a ~+0.35 stops en sombras)
        if shadows != 0.0:
            s_factor = 1.0 + (shadows / 100.0) * 0.55 * shadow_mask
            lin *= s_factor[..., np.newaxis]

        # Highlights recovery (-10 en LR comprime altas luces)
        if highlights != 0.0:
            h_factor = 1.0 + (highlights / 100.0) * 0.35 * highlight_mask
            lin *= h_factor[..., np.newaxis]

        # 5. Retorno a sRGB con mapeo de tonos
        srgb = np.power(np.clip(lin, 0.0, 1.0), 1.0 / 2.2)

        # 6. Blacks y Whites
        if blacks != 0.0:
            b_offset = (blacks / 100.0) * 0.05
            srgb = np.clip(srgb + b_offset, 0.0, 1.0)
        if whites != 0.0:
            w_factor = 1.0 + (whites / 100.0) * 0.06
            srgb = np.clip(srgb * w_factor, 0.0, 1.0)

        # 7. Curva tonal ToneCurvePV2012 de GutoPro Day Boy: (0,0), (177, 183), (255, 255)
        # Sutil levantamiento en medios tonos altos (+6 niveles)
        lut_in = np.array([0, 177, 255], dtype=np.float32)
        lut_out = np.array([0, 183, 255], dtype=np.float32)
        srgb_255 = np.clip(srgb * 255.0, 0, 255).astype(np.uint8)
        
        # Crear LUT de 256 niveles
        x_vals = np.arange(256, dtype=np.float32)
        curve_lut = np.interp(x_vals, lut_in, lut_out).astype(np.uint8)
        srgb_curved = cv2.LUT(srgb_255, curve_lut)

        # 8. Contraste y Vibrance / Saturación
        # HSV para ajuste fino de saturación
        hsv = cv2.cvtColor(srgb_curved, cv2.COLOR_RGB2HSV).astype(np.float32)
        
        # Vibrance: satura más los tonos menos saturados sin sobre-saturar la piel
        sat = hsv[..., 1] / 255.0
        vib_boost = (1.0 - sat) * (vibrance / 100.0) * 0.30
        hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + vib_boost) * (1.0 + saturation / 200.0), 0, 255)

        # HSL Luminance Adjustment Green +26, Orange +5 (piel luminosa y follaje vivo)
        hues = hsv[..., 0] # 0-180 en OpenCV
        # Piel / Naranja: hue ~10 a 25
        orange_mask = (hues >= 8) & (hues <= 25)
        hsv[..., 2][orange_mask] = np.clip(hsv[..., 2][orange_mask] * 1.04, 0, 255)
        # Verdes: hue ~35 a 85
        green_mask = (hues >= 35) & (hues <= 85)
        hsv[..., 2][green_mask] = np.clip(hsv[..., 2][green_mask] * 1.10, 0, 255)

        final_rgb = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
        return final_rgb
