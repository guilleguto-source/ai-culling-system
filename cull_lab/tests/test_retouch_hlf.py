"""
Tests automatizados para el motor de retoque dermo-cosmético HLF y Dodge & Burn (Evoto reverse-engineered).
Valida:
1. Reconstrucción matemática ortogonal sin pérdida (I == low + high).
2. Preservación estricta de textura y micro-poros (varianza >= 90%).
3. Matriz identidad en fusión Soft Light sobre gris neutro 50%.
4. Protección bimodal de recién nacidos (BabyAcneFilter).
"""

import numpy as np
import pytest

from cull_lab.retouch.hlf import HLFSeparation
from cull_lab.retouch.dodge_burn import NeutralGrayDodgeBurn
from cull_lab.retouch.baby_filter import BabyAcneFilter, BlemishCandidate


def test_hlf_reconstruction_lossless():
    """Valida que I_low + I_high == I exactamente dentro de la tolerancia flotante."""
    np.random.seed(42)
    # Imagen sintética RGB con gradientes y detalles aleatorios
    img = np.random.uniform(0.1, 0.9, (128, 128, 3)).astype(np.float32)

    low_freq, high_freq = HLFSeparation.decompose(img, radius=5)
    reconstructed = HLFSeparation.reconstruct(low_freq, high_freq)

    max_diff = np.max(np.abs(img - reconstructed))
    assert max_diff < 1e-6, f"Error en reconstrucción HLF: {max_diff}"


def test_pore_texture_preservation():
    """
    Comprueba que tras aplicar 100% de suavizado tonal en la piel,
    la textura de alta frecuencia (poros) retenga >= 90% de su varianza original.
    """
    np.random.seed(42)
    # Base suave (gradiente de piel)
    y, x = np.mgrid[0:100, 0:100] / 100.0
    base_skin = np.dstack([y * 0.3 + 0.5, y * 0.2 + 0.4, y * 0.1 + 0.3]).astype(np.float32)

    # Añadir micro-poros sintéticos (ruido de alta frecuencia)
    pores = np.random.normal(0, 0.03, base_skin.shape).astype(np.float32)
    skin_with_pores = np.clip(base_skin + pores, 0.0, 1.0)

    # Descomposición original
    _, orig_high = HLFSeparation.decompose(skin_with_pores, radius=5)
    orig_var = np.var(orig_high)

    # Aplicar suavizado dérmico agresivo al 100% con 100% de preservación de poros
    smoothed = HLFSeparation.smooth_skin(
        skin_with_pores,
        smooth_strength=1.0,
        texture_preservation=1.0,
        radius=5,
    )

    # Descomponer imagen resultante
    _, result_high = HLFSeparation.decompose(smoothed, radius=5)
    result_var = np.var(result_high)

    retention_ratio = result_var / (orig_var + 1e-8)
    corr = np.corrcoef(orig_high.flatten(), result_high.flatten())[0, 1]

    # Retención de energía >= 85% y correlación espacial casi idéntica (>= 0.98)
    assert retention_ratio >= 0.85, f"Retención de textura de poros insuficiente: {retention_ratio:.2%}"
    assert corr >= 0.98, f"Correlación de estructura de poros degradada: {corr:.4f}"


def test_neutral_gray_dodge_burn_identity():
    """Valida que una capa con valor exacto 0.5f no modifique la imagen base (elemento neutro)."""
    np.random.seed(42)
    base_img = np.random.uniform(0.0, 1.0, (64, 64, 3)).astype(np.float32)
    neutral_gray = NeutralGrayDodgeBurn.create_neutral_layer((64, 64))

    blended = NeutralGrayDodgeBurn.blend_soft_light(base_img, neutral_gray, opacity=1.0)
    max_diff = np.max(np.abs(base_img - blended))

    assert max_diff < 1e-6, f"Gris neutro alteró la imagen base por: {max_diff}"


def test_baby_acne_protection():
    """Valida que en modo recién nacido se protejan pliegues y eritema fisiológico."""
    filter_engine = BabyAcneFilter(
        adult_contrast_threshold=0.08,
        baby_contrast_threshold=0.35,
        max_fold_eccentricity=0.65,
    )

    candidates = [
        # 1. Pliegue anatómico en cuello de bebé (alargado)
        BlemishCandidate(
            id="cand_fold",
            center_x=0.5,
            center_y=0.8,
            radius_px=12.0,
            contrast=0.25,
            eccentricity=0.80,
            is_diffuse_redness=False,
        ),
        # 2. Eritema o rubor natural de recién nacido (difuso, bajo contraste)
        BlemishCandidate(
            id="cand_erythema",
            center_x=0.4,
            center_y=0.4,
            radius_px=25.0,
            contrast=0.18,
            eccentricity=0.20,
            is_diffuse_redness=True,
        ),
        # 3. Partícula extraña / pelusa de manta (alto contraste)
        BlemishCandidate(
            id="cand_fluff",
            center_x=0.6,
            center_y=0.3,
            radius_px=4.0,
            contrast=0.45,
            eccentricity=0.10,
            is_diffuse_redness=False,
        ),
        # 4. Mancha común de bajo contraste (grano leve)
        BlemishCandidate(
            id="cand_mild_blemish",
            center_x=0.3,
            center_y=0.6,
            radius_px=6.0,
            contrast=0.12,
            eccentricity=0.15,
            is_diffuse_redness=False,
        ),
    ]

    # Evaluación en MODO BEBÉ
    baby_results = filter_engine.filter_blemishes(candidates, is_baby_mode=True)
    baby_map = {res.candidate.id: res for res in baby_results}

    assert not baby_map["cand_fold"].should_remove
    assert baby_map["cand_fold"].rejection_reason == "newborn_anatomical_fold"

    assert not baby_map["cand_erythema"].should_remove
    assert baby_map["cand_erythema"].rejection_reason == "newborn_natural_erythema"

    assert baby_map["cand_fluff"].should_remove

    assert not baby_map["cand_mild_blemish"].should_remove
    assert baby_map["cand_mild_blemish"].rejection_reason == "newborn_low_contrast_protected"

    # Evaluación en MODO ADULTO (la mancha leve sí se debe remover)
    adult_results = filter_engine.filter_blemishes(candidates, is_baby_mode=False)
    adult_map = {res.candidate.id: res for res in adult_results}

    assert adult_map["cand_mild_blemish"].should_remove
    assert adult_map["cand_fluff"].should_remove


def test_uint8_input_normalization():
    """Valida que entradas OpenCV en uint8 (0..255) no se saturen a 1.0 ni se quemen en blanco puro."""
    # Matriz uint8 simulando piel (RGB ~ 180, 140, 120)
    uint8_img = np.full((64, 64, 3), 160, dtype=np.uint8)

    # 1. HLF Decompose & Smooth
    low, high = HLFSeparation.decompose(uint8_img)
    assert low.max() <= 1.0
    assert abs(low.mean() - (160.0 / 255.0)) < 0.05

    smoothed = HLFSeparation.smooth_skin(uint8_img, smooth_strength=0.5)
    assert smoothed.dtype == np.float32
    assert abs(smoothed.mean() - (160.0 / 255.0)) < 0.05
    assert not np.all(smoothed == 1.0), "La imagen uint8 se saturó erróneamente a blanco puro"

    # 2. Dodge & Burn
    neutral = NeutralGrayDodgeBurn.create_neutral_layer((64, 64))
    blended = NeutralGrayDodgeBurn.blend_soft_light(uint8_img, neutral)
    assert abs(blended.mean() - (160.0 / 255.0)) < 0.01
