"""
test_portrait_relighting.py — Tests para el módulo de re-iluminación facial.
"""
from services.portrait_relighting import (
    calculate_face_relighting,
    build_relighting_xmp_elements,
)


def test_calculate_face_relighting():
    bboxes = [[100, 100, 200, 200], [500, 300, 150, 150]]
    proposals = calculate_face_relighting(bboxes, img_width=1000, img_height=1000, intensity=0.8)
    assert len(proposals) == 2
    assert proposals[0].center_x == 0.2
    assert proposals[0].center_y == 0.2
    assert proposals[0].exposure_boost > 0


def test_build_relighting_xmp_elements():
    bboxes = [[100, 100, 200, 200]]
    proposals = calculate_face_relighting(bboxes, img_width=1000, img_height=1000)
    elements = build_relighting_xmp_elements(proposals)
    assert len(elements) == 1
    assert "PaintBasedCorrections" in elements[0].tag
