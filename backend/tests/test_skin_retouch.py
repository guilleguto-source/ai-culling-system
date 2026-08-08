"""
test_skin_retouch.py — Tests para el módulo de retoque y suavizado de piel.
"""
from services.skin_retouch import (
    calculate_skin_retouch,
    build_skin_retouch_xmp_elements,
)


def test_calculate_skin_retouch_active():
    prop = calculate_skin_retouch(has_skin=True, smoothness=0.6)
    assert prop.skin_detected is True
    assert prop.local_clarity < 0
    assert prop.local_texture < 0


def test_calculate_skin_retouch_no_skin():
    prop = calculate_skin_retouch(has_skin=False)
    assert prop.skin_detected is False
    assert prop.local_clarity == 0


def test_build_skin_retouch_xmp_elements():
    prop = calculate_skin_retouch(has_skin=True, smoothness=0.5)
    elements = build_skin_retouch_xmp_elements(prop)
    assert len(elements) == 1
    assert "PaintBasedCorrections" in elements[0].tag
