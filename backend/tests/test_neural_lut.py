"""
test_neural_lut.py — Tests unitarios para el motor Neural LUT y color grading adaptativo.
"""
from services.neural_lut import (
    compute_lut_adjustments,
    get_learned_style,
    get_lut_status,
    list_available_luts,
    load_lut_profile,
)


def test_list_available_luts():
    luts = list_available_luts()
    assert len(luts) >= 4
    names = [lut["name"] for lut in luts]
    assert "warm_golden" in names
    assert "cool_indoor" in names
    assert "flat_matte" in names


def test_load_lut_profile():
    lut = load_lut_profile("warm_golden")
    assert lut
    assert "settings" in lut
    assert "Contrast2012" in lut["settings"]


def test_get_learned_style_custom_override():
    settings, source = get_learned_style(custom_lut="flat_matte")
    assert "custom:flat_matte" in source
    assert settings.get("Contrast2012") == -12


def test_compute_lut_adjustments_strength():
    # 100% strength
    adj_100 = compute_lut_adjustments(custom_lut="warm_golden", strength=1.0)
    # 50% strength
    adj_50 = compute_lut_adjustments(custom_lut="warm_golden", strength=0.5)

    assert adj_100.get("Contrast2012") == 8
    assert adj_50.get("Contrast2012") == 4


def test_get_lut_status():
    status = get_lut_status()
    assert "available_luts" in status
    assert "total_learned_scenes" in status
