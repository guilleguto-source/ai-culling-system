"""
test_crop_style_integration.py — Tests para la integración del estilo aprendido de reencuadre (Fase 3 / Fase K).
"""
import pytest
from services.auto_crop import propose_crop

W, H = 1600, 1067


def _face(cx: float, cy: float, size: int = 160) -> list[int]:
    return [int(cx * W - size / 2), int(cy * H - size / 2), size, size]


def _lms(face: list[int], nose_offset: float = 0.0) -> list[list[int]]:
    x, y, fw, fh = face
    le = [x + int(fw * 0.3), y + int(fh * 0.4)]
    re = [x + int(fw * 0.7), y + int(fh * 0.4)]
    eye_dist = re[0] - le[0]
    nose = [int((le[0] + re[0]) / 2 + nose_offset * eye_dist), y + int(fh * 0.65)]
    return [le, re, nose, [le[0], y + fh - 10], [re[0], y + fh - 10]]


def test_crop_style_influences_target():
    """El estilo aprendido debe desplazar suavemente el objetivo de composición hacia la preferencia."""
    face = _face(0.5, 0.5)
    lms = _lms(face)
    
    # 1. Sin estilo aprendido
    prop_default = propose_crop(
        scene_type="portrait",
        face_bboxes=[face],
        eye_landmarks=[lms],
        saliency_region=None,
        img_shape=(H, W),
        level="medio",
        horizon_angle=0.0,
        person_bboxes=None,
        img_rgb=None,
        crop_style=None,
    )
    assert prop_default is not None
    
    # 2. Con estilo aprendido
    crop_style = {
        "portrait": {
            "offset_x": 0.4,
            "offset_y": 0.4,
            "area": 0.85,
        }
    }
    prop_styled = propose_crop(
        scene_type="portrait",
        face_bboxes=[face],
        eye_landmarks=[lms],
        saliency_region=None,
        img_shape=(H, W),
        level="medio",
        horizon_angle=0.0,
        person_bboxes=None,
        img_rgb=None,
        crop_style=crop_style,
    )
    assert prop_styled is not None
    assert "estilo aprendido" in prop_styled.reason
    assert (prop_styled.top != prop_default.top or prop_styled.left != prop_default.left)
