"""
test_tonal_rescue.py — Tests para el módulo de rescate tonal (Fase 3).
"""
import numpy as np
import pytest
from services.tonal_rescue import (
    analyze_tonal_range,
    suggest_tonal_adjustments,
    TonalReport,
    HIGHLIGHTS_CLIP_THRESHOLD,
    SHADOWS_CLIP_THRESHOLD,
    MAX_HIGHLIGHTS_CORRECTION,
    MAX_SHADOWS_CORRECTION,
)


def test_no_intervention_balanced_photo():
    """Una foto con histograma centrado y balanceado no debe recibir ajustes."""
    # Imagen gris medio uniforme (128 en sRGB)
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    report = analyze_tonal_range(img)
    
    assert report.highlights_clip < HIGHLIGHTS_CLIP_THRESHOLD
    assert report.shadows_clip < SHADOWS_CLIP_THRESHOLD
    
    adjustments = suggest_tonal_adjustments(report)
    assert adjustments == {}


def test_highlights_rescue_severe():
    """Una foto con altas luces quemadas (>15% píxeles blancos) debe sugerir Highlights negativos."""
    img = np.full((100, 100, 3), 120, dtype=np.uint8)
    # 20% de la imagen en blanco puro quemado (255)
    img[:20, :] = 255
    
    report = analyze_tonal_range(img)
    assert report.highlights_clip >= 0.15
    
    adjustments = suggest_tonal_adjustments(report)
    assert "Highlights2012" in adjustments
    assert "Whites2012" in adjustments
    assert adjustments["Highlights2012"] < 0
    assert adjustments["Highlights2012"] <= -40  # corrección significativa
    assert adjustments["Whites2012"] < 0


def test_shadows_rescue_severe():
    """Una foto con sombras muy empastadas (>25% píxeles negros) debe sugerir Shadows positivos."""
    img = np.full((100, 100, 3), 140, dtype=np.uint8)
    # 30% de la imagen en negro puro (0)
    img[:30, :] = 0
    
    report = analyze_tonal_range(img)
    assert report.shadows_clip >= 0.25
    
    adjustments = suggest_tonal_adjustments(report)
    assert "Shadows2012" in adjustments
    assert "Blacks2012" in adjustments
    assert adjustments["Shadows2012"] > 0
    assert adjustments["Shadows2012"] >= 30
    assert adjustments["Blacks2012"] > 0


def test_high_contrast_both_rescues():
    """Foto de altísimo contraste con zonas quemadas y sombras profundas a la vez."""
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    img[:15, :] = 255  # 15% quemado
    img[80:, :] = 0    # 20% negro
    
    report = analyze_tonal_range(img)
    adjustments = suggest_tonal_adjustments(report)
    
    assert "Highlights2012" in adjustments
    assert "Shadows2012" in adjustments
    assert adjustments["Highlights2012"] < 0
    assert adjustments["Shadows2012"] > 0


def test_smooth_scaling_limits():
    """Verifica que los ajustes respeten los límites máximos definidos."""
    # Caso extremo: 100% quemada
    rep_white = TonalReport(highlights_clip=1.0, shadows_clip=0.0, midtone_lum=1.0, has_faces=False)
    adj_white = suggest_tonal_adjustments(rep_white)
    assert adj_white["Highlights2012"] == MAX_HIGHLIGHTS_CORRECTION
    
    # Caso extremo: 100% negra
    rep_black = TonalReport(highlights_clip=0.0, shadows_clip=1.0, midtone_lum=0.0, has_faces=False)
    adj_black = suggest_tonal_adjustments(rep_black)
    assert adj_black["Shadows2012"] == MAX_SHADOWS_CORRECTION
