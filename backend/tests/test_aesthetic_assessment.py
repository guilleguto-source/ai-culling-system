"""
test_aesthetic_assessment.py — Tests unitarios para el motor estético de 7 ejes.
"""
import numpy as np
import cv2
import pytest
from services.aesthetic_assessment import (
    AestheticBreakdown,
    evaluate_aesthetics_detailed,
    evaluate_aesthetics_fast,
    compute_colorfulness,
    compute_rule_of_thirds_score,
    compute_dynamic_range_score,
    compute_subject_isolation_score,
    compute_lighting_quality_score,
    compute_composition_balance_score,
    compute_leading_lines_score,
)


def test_aesthetic_breakdown_ranges():
    """Genera una imagen sintética y valida que todos los 7 ejes estén acotados [0.0, 1.0]."""
    rng = np.random.default_rng(42)
    img = rng.integers(50, 200, size=(256, 256, 3), dtype=np.uint8)
    
    breakdown = evaluate_aesthetics_detailed(img)
    assert isinstance(breakdown, AestheticBreakdown)
    d = breakdown.to_dict()
    
    assert 0.0 <= d["rule_of_thirds"] <= 1.0
    assert 0.0 <= d["color_harmony"] <= 1.0
    assert 0.0 <= d["dynamic_range"] <= 1.0
    assert 0.0 <= d["subject_isolation"] <= 1.0
    assert 0.0 <= d["lighting_quality"] <= 1.0
    assert 0.0 <= d["composition_balance"] <= 1.0
    assert 0.0 <= d["leading_lines"] <= 1.0
    assert 0.0 <= d["overall_score"] <= 1.0


def test_rule_of_thirds_saliency_at_intersection():
    """Una imagen con alto contraste en un punto de tercio debe puntuar más alto que plana."""
    flat_img = np.full((180, 180), 128, dtype=np.uint8)
    thirds_img = np.full((180, 180), 128, dtype=np.uint8)
    
    # Dibujar punto de contraste alto en la intersección de tercios (x=60, y=60)
    cv2.circle(thirds_img, (60, 60), 15, 255, -1)
    
    score_flat = compute_rule_of_thirds_score(flat_img)
    score_thirds = compute_rule_of_thirds_score(thirds_img)
    assert score_thirds > score_flat


def test_color_harmony_vibrant_vs_grayscale():
    """Una imagen colorida debe tener mayor color harmony que una imagen monocromática."""
    gray_like = np.full((100, 100, 3), 128, dtype=np.uint8)
    
    # Imagen con paleta viva (cielo azul + campo verde)
    vibrant = np.zeros((100, 100, 3), dtype=np.uint8)
    vibrant[:50, :, 0] = 30; vibrant[:50, :, 1] = 144; vibrant[:50, :, 2] = 255 # azul
    vibrant[50:, :, 0] = 34; vibrant[50:, :, 1] = 139; vibrant[50:, :, 2] = 34  # verde
    
    bd_gray = evaluate_aesthetics_detailed(gray_like)
    bd_vibrant = evaluate_aesthetics_detailed(vibrant)
    assert bd_vibrant.color_harmony > bd_gray.color_harmony


def test_leading_lines_score():
    """Líneas diagonales nítidas deben obtener mayor coherencia direccional que ruido uniforme."""
    lines_img = np.zeros((120, 120), dtype=np.uint8)
    for i in range(0, 120, 15):
        cv2.line(lines_img, (0, i), (i, 120), 255, 2)
        
    rng = np.random.default_rng(10)
    noise_img = rng.integers(0, 255, size=(120, 120), dtype=np.uint8)
    
    score_lines = compute_leading_lines_score(lines_img)
    score_noise = compute_leading_lines_score(noise_img)
    assert score_lines > score_noise


def test_evaluate_aesthetics_fast_backward_compatibility():
    """Verifica que evaluate_aesthetics_fast devuelve float o tuple correctamente."""
    img = np.full((100, 100, 3), 150, dtype=np.uint8)
    score = evaluate_aesthetics_fast(img)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    
    feat = evaluate_aesthetics_fast(img, return_features=True)
    assert isinstance(feat, tuple) and len(feat) == 3
