"""
test_pre_edit_skin.py — Tests para la estimación de balance de blancos ponderada por piel.
"""
import numpy as np
import pytest
from services.pre_edit import estimate_wb, _skin_patches, measure_luminance


def test_skin_weighted_multi_face():
    """Un rostro grande (protagonista) debe tener mayor peso en el WB que un rostro pequeño."""
    img = np.full((500, 500, 3), 30, dtype=np.uint8)
    
    # Cara grande protagonista: piel neutra ideal (B/R ~ 0.62)
    large_bbox = [50, 50, 200, 200]  # area 40000
    img[50:250, 50:250] = (190, 140, 118)
    
    # Cara pequeña secundaria en sombra o luz tintada
    small_bbox = [350, 350, 40, 40]   # area 1600
    img[350:390, 350:390] = (120, 180, 100) # muy verdosa
    
    # Estimación combinada
    wb = estimate_wb(img, [large_bbox, small_bbox])
    assert wb is not None
    temp, tint = wb
    # El balance general debe mantenerse cerca de la cara grande dominante
    assert abs(temp) < 10.0
    assert abs(tint) < 15.0


def test_skin_specular_rejection():
    """Los brillos especulares dentro del patch no deben falsear el cálculo."""
    img = np.full((300, 300, 3), 40, dtype=np.uint8)
    bbox = [50, 50, 100, 100]
    img[50:150, 50:150] = (190, 140, 118)
    
    # Introducir brillo blanco quemado en la nariz (255, 255, 255)
    img[85:95, 85:95] = 255
    
    patches = _skin_patches(img, [bbox])
    assert patches is not None
    # Los pixeles a 255 deben haber sido filtrados
    assert not np.any(patches.max(axis=-1) >= 250)
