"""
Pruebas automatizadas de geometría, nivelación de horizonte y smart crop (Fase 3).
"""

import math
import tempfile
from pathlib import Path

from cull_lab.core.xmp_exporter import MetadataDelta, XmpExporter
from cull_lab.editing.smart_crop import CropCoordinates, SmartCropper, SubjectBBox
from cull_lab.editing.straighten import LineSegment, StraightenDetector


def test_horizon_angle_detection():
    """Valida la detección angular exacta sobre líneas de horizonte sintéticas (+3.5°)."""
    detector = StraightenDetector()

    target_angle = 3.5  # Inclinación en grados
    rad = math.radians(target_angle)

    # Crear 3 segmentos con ángulo exacto de 3.5°
    segments = [
        LineSegment(x1=100.0, y1=200.0, x2=600.0, y2=200.0 + (500.0 * math.tan(rad))),
        LineSegment(x1=200.0, y1=400.0, x2=800.0, y2=400.0 + (600.0 * math.tan(rad))),
        LineSegment(x1=50.0, y1=150.0, x2=350.0, y2=150.0 + (300.0 * math.tan(rad))),
        # Línea de ruido transversal (outlier de 45°)
        LineSegment(x1=100.0, y1=100.0, x2=200.0, y2=200.0),
    ]

    res = detector.estimate_tilt_from_segments(segments)
    assert res.needs_straighten is True
    assert abs(res.tilt_angle_degrees - target_angle) < 0.1
    assert res.horizontal_lines_count >= 3
    assert res.confidence > 0.6


def test_deadband_ignores_micro_tilt():
    """Valida que inclinaciones minúsculas (< 0.2°) se ignoren para no introducir rotaciones espurias."""
    detector = StraightenDetector(deadband_threshold_degrees=0.20)

    # Inclinación de 0.10°
    rad = math.radians(0.10)
    segments = [
        LineSegment(x1=100.0, y1=200.0, x2=800.0, y2=200.0 + (700.0 * math.tan(rad))),
    ]

    res = detector.estimate_tilt_from_segments(segments)
    assert res.needs_straighten is False
    assert res.tilt_angle_degrees == 0.0


def test_maximal_inscribed_crop_bounds():
    """Valida que el cálculo analítico de recorte elimine esquinas vacías al rotar."""
    cropper = SmartCropper()

    # Imagen 6000x4000 rotada 5.0 grados
    crop = cropper.compute_crop(image_width=6000, image_height=4000, tilt_angle_degrees=5.0)

    # Debe ser menor a 1.0 (recortado para no mostrar bordes negros)
    assert crop.width < 1.0
    assert crop.height < 1.0
    assert crop.top > 0.0
    assert crop.left > 0.0
    assert crop.bottom < 1.0
    assert crop.right < 1.0

    # Si el ángulo es 0°, debe cubrir el 100%
    zero_crop = cropper.compute_crop(image_width=6000, image_height=4000, tilt_angle_degrees=0.0)
    assert abs(zero_crop.width - 1.0) < 1e-4
    assert abs(zero_crop.height - 1.0) < 1e-4
    assert zero_crop.top == 0.0
    assert zero_crop.left == 0.0


def test_portrait_orientation_inscribed_crop():
    """Valida que en orientación vertical (R < 1, ej. 4000x6000) el recorte no sobrepase los bordes rotados."""
    import math

    cropper = SmartCropper()
    w, h = 4000, 6000
    angle = 6.0
    crop = cropper.compute_crop(image_width=w, image_height=h, tilt_angle_degrees=angle)

    # Dimensiones absolutas del recorte
    cw = crop.width * w
    ch = crop.height * h

    rad = math.radians(angle)
    # Comprobación de que la caja rotada del recorte cabe dentro del marco original
    proj_w = cw * math.cos(rad) + ch * math.sin(rad)
    proj_h = cw * math.sin(rad) + ch * math.cos(rad)

    assert proj_w <= w + 1e-3, f"Ancho proyectado excede marco vertical: {proj_w} > {w}"
    assert proj_h <= h + 1e-3, f"Alto proyectado excede marco vertical: {proj_h} > {h}"


def test_subject_aware_headroom():
    """Valida que el encuadre inteligente respete la cabeza del sujeto sin decapitarlo."""
    cropper = SmartCropper()

    # Sujeto ubicado en la parte superior-central: cabeza en ymin = 0.12
    subject = SubjectBBox(xmin=0.40, ymin=0.12, xmax=0.60, ymax=0.55)

    crop = cropper.compute_crop(
        image_width=6000,
        image_height=4000,
        tilt_angle_degrees=4.0,
        subjects=[subject],
        headroom_ratio=0.03,
    )

    # El borde superior del recorte DEBE estar por encima de la cabeza del sujeto (top < 0.12)
    assert crop.top <= subject.ymin
    # El sujeto debe estar contenido horizontalmente dentro del recorte
    assert crop.left <= subject.xmin
    assert crop.right >= subject.xmax


def test_xmp_crs_crop_persistence():
    """Valida la persistencia e integración completa con XmpExporter (crs:CropAngle y crs:Crop*)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xmp_path = Path(tmpdir) / "STRAIGHTEN_TEST.xmp"

        cropper = SmartCropper()
        crop = cropper.compute_crop(image_width=6000, image_height=4000, tilt_angle_degrees=3.25)

        delta = MetadataDelta(
            crop_angle=3.25,
            has_crop=True,
            crop_coords=crop.as_tuple(),
        )

        res_path = XmpExporter.apply_delta(xmp_path, delta)
        assert res_path.exists()

        # Leer y verificar metadatos normalizados
        meta = XmpExporter.read_metadata(xmp_path)
        assert abs(meta["crop_angle"] - 3.25) < 1e-3
        assert meta["has_crop"] is True


if __name__ == "__main__":
    test_horizon_angle_detection()
    test_deadband_ignores_micro_tilt()
    test_maximal_inscribed_crop_bounds()
    test_subject_aware_headroom()
    test_xmp_crs_crop_persistence()
    print("¡Todas las pruebas de geometría y smart crop pasaron exitosamente!")
