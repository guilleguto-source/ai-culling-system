"""
test_vip_culling.py — Pruebas unitarias para Culling Jerárquico VIP, Mirada y Sonrisa Condicional.
"""
import pytest
from services.face_assessment import compute_biometric_face_attributes
from services.cluster_gates import (
    apply_technical_gates_explained,
    compute_vip_weights,
    GATE_OJOS,
    GATE_MIRADA,
    GATE_SONRISA_VIP,
)


def test_biometric_face_attributes_centered_gaze():
    """Rostro con iris centrado debe dar gaze_score alto y gaze_out False."""
    landmarks = [type("Point", (), {"x": 0.5, "y": 0.5})() for _ in range(478)]
    # Ojo izquierdo outer=33, inner=133. Ancho = 0.20
    landmarks[33].x = 0.40
    landmarks[133].x = 0.60
    # Iris centrado en 0.50 -> ratio = 0.50, Y centrado en 0.475
    landmarks[468].x = 0.50
    landmarks[468].y = 0.475

    # Ojo derecho outer=362, inner=263. Ancho = 0.20
    landmarks[362].x = 0.70
    landmarks[263].x = 0.90
    landmarks[473].x = 0.80
    landmarks[473].y = 0.475

    # Párpados abiertos (EAR ~ 0.25)
    landmarks[159].y = 0.45
    landmarks[145].y = 0.50
    landmarks[386].y = 0.45
    landmarks[374].y = 0.50

    attrs = compute_biometric_face_attributes(landmarks)
    assert attrs["eyes_closed"] is False
    assert attrs["gaze_out"] is False
    assert attrs["gaze_score"] > 0.85


def test_biometric_face_attributes_deviated_gaze():
    """Rostro mirando al costado debe marcar gaze_out True."""
    landmarks = [type("Point", (), {"x": 0.5, "y": 0.5})() for _ in range(478)]
    landmarks[33].x = 0.40
    landmarks[133].x = 0.60
    # Iris desplazado hacia el canto (ratio = 0.10)
    landmarks[468].x = 0.42
    landmarks[362].x = 0.70
    landmarks[263].x = 0.90
    landmarks[473].x = 0.72

    landmarks[159].y = 0.45
    landmarks[145].y = 0.50
    landmarks[386].y = 0.45
    landmarks[374].y = 0.50

    attrs = compute_biometric_face_attributes(landmarks)
    assert attrs["gaze_out"] is True


def test_vip_immunity_over_secondary_blinking():
    """
    Foto 0: VIP mirando y con ojos abiertos, pero secundario al fondo parpadeando.
    Foto 1: VIP con ojos cerrados, secundario con ojos abiertos.
    Resultado: Foto 0 DEBE GANAR; Foto 1 debe ser descartada por ojos cerrados del VIP.
    """
    indices = [0, 1]
    # Foto 0: Cara 0 (VIP, abierta), Cara 1 (Secundario, cerrada)
    # Foto 1: Cara 0 (VIP, cerrada), Cara 1 (Secundario, abierta)
    face_attrs = [
        [
            {"valid": True, "ear": 0.28, "blink": 0.0, "yaw": 0.0, "gaze_out": False},
            {"valid": True, "ear": 0.08, "blink": 0.9, "yaw": 0.0, "gaze_out": False},
        ],
        [
            {"valid": True, "ear": 0.08, "blink": 0.9, "yaw": 0.0, "gaze_out": False},
            {"valid": True, "ear": 0.28, "blink": 0.0, "yaw": 0.0, "gaze_out": False},
        ],
    ]
    face_sharp = [[500.0, 500.0], [500.0, 500.0]]
    face_bboxes = [[[100, 100, 200, 200], [400, 400, 50, 50]], [[100, 100, 200, 200], [400, 400, 50, 50]]]
    face_identities = [[1, 2], [1, 2]]
    vip_ids = {1}  # Identidad 1 es el VIP

    survivors, motivos = apply_technical_gates_explained(
        indices, face_attrs, face_sharp, face_bboxes,
        face_identities_list=face_identities,
        vip_identity_ids=vip_ids,
    )

    assert survivors == [0]
    assert motivos[1] == GATE_OJOS


def test_conditional_vip_smile_relaxation_active():
    """
    Caso niños 2-5 años: cuando vip_smile_relaxed=True, una foto con VIP serio
    NO debe ser descartada si no hay sonrisa en el evento.
    """
    indices = [0, 1]
    face_attrs = [
        [{"valid": True, "ear": 0.25, "blink": 0.0, "yaw": 0.0, "gaze_out": False, "smile": True, "smile_score": 0.8}],
        [{"valid": True, "ear": 0.25, "blink": 0.0, "yaw": 0.0, "gaze_out": False, "smile": False, "smile_score": 0.0}],
    ]
    face_sharp = [[500.0], [500.0]]
    face_bboxes = [[[100, 100, 200, 200]], [[100, 100, 200, 200]]]
    face_identities = [[1], [1]]
    vip_ids = {1}

    # Con relajación activa: ambas sobreviven al gate técnico (la sonrisa es opcional)
    survivors_relaxed, _ = apply_technical_gates_explained(
        indices, face_attrs, face_sharp, face_bboxes,
        face_identities_list=face_identities,
        vip_identity_ids=vip_ids,
        vip_smile_relaxed=True,
    )
    assert 0 in survivors_relaxed and 1 in survivors_relaxed

    # Con relajación apagada (adultos/niños sonrientes): la foto sin sonrisa es descartada
    survivors_strict, motivos_strict = apply_technical_gates_explained(
        indices, face_attrs, face_sharp, face_bboxes,
        face_identities_list=face_identities,
        vip_identity_ids=vip_ids,
        vip_smile_relaxed=False,
    )
    assert survivors_strict == [0]
    assert motivos_strict[1] == GATE_SONRISA_VIP
