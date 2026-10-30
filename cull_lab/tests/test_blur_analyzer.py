"""
Pruebas automatizadas para el discriminador de blur y bokeh (blur_analyzer.py).
"""

from cull_lab.culling.blur_analyzer import BlurAnalyzer


def test_portrait_bokeh_f14_acceptable():
    """Valida que un retrato f/1.4 con sujeto nítido y fondo cremoso se apruebe y no se rechace."""
    analyzer = BlurAnalyzer()

    # Sujeto muy nítido (var 1500), fondo cremoso bokeh (var 25), dispersión normal (0.7)
    res = analyzer.analyze_blur(
        subject_laplacian_var=1500.0,
        background_laplacian_var=25.0,
        gradient_angle_dispersion=0.70,
    )

    assert res.is_acceptable_for_cull is True
    assert res.is_bokeh_intentional is True
    assert res.is_motion_blur is False
    assert res.is_missed_focus is False
    assert res.recommended_sharpen_scope == "Subject"
    assert res.subject_sharpness > 8.0
    assert res.background_sharpness < 3.0


def test_camera_motion_blur_rejected():
    """Valida que la trepidación (movimiento direccional uniforme) se detecte y rechace."""
    analyzer = BlurAnalyzer()

    # Sujeto borroso (var 70), fondo borroso, dispersión angular muy baja (0.15 = alta coherencia)
    res = analyzer.analyze_blur(
        subject_laplacian_var=70.0,
        background_laplacian_var=60.0,
        gradient_angle_dispersion=0.15,
    )

    assert res.is_acceptable_for_cull is False
    assert res.is_motion_blur is True
    assert res.is_missed_focus is False
    assert res.directional_coherence >= 0.80
    assert res.recommended_sharpen_scope == "None"


def test_missed_focus_rejected():
    """Valida que el foco perdido (sin trepidación, desenfoque radial isotrópico) se detecte."""
    analyzer = BlurAnalyzer()

    # Sujeto borroso (var 50), dispersión angular aleatoria/isotrópica (0.85 = baja coherencia)
    res = analyzer.analyze_blur(
        subject_laplacian_var=50.0,
        background_laplacian_var=50.0,
        gradient_angle_dispersion=0.85,
    )

    assert res.is_acceptable_for_cull is False
    assert res.is_motion_blur is False
    assert res.is_missed_focus is True
    assert res.directional_coherence < 0.20


def test_sharp_landscape_all():
    """Valida que un paisaje nítido en f/8 apruebe enfoque global 'All'."""
    analyzer = BlurAnalyzer()

    # Ambos muy nítidos
    res = analyzer.analyze_blur(
        subject_laplacian_var=1800.0,
        background_laplacian_var=1600.0,
        gradient_angle_dispersion=0.75,
    )

    assert res.is_acceptable_for_cull is True
    assert res.is_bokeh_intentional is False
    assert res.recommended_sharpen_scope == "All"


if __name__ == "__main__":
    test_portrait_bokeh_f14_acceptable()
    test_camera_motion_blur_rejected()
    test_missed_focus_rejected()
    test_sharp_landscape_all()
    print("¡Todas las pruebas de discriminación de blur pasaron exitosamente!")
