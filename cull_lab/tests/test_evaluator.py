"""
Pruebas automatizadas de la matriz contextual ocular y foco en evaluator.py.
"""

from cull_lab.culling.evaluator import (
    ContextualFaceEvaluator,
    FaceObservation,
    RawEyeState,
)


def test_accidental_mid_blink_penalized():
    """Valida que un parpadeo a medio cerrar reciba penalización severa (-0.5)."""
    obs = FaceObservation(
        face_id="F1",
        bbox=(0.1, 0.1, 0.3, 0.4),
        left_eye_state=RawEyeState.OPEN,
        right_eye_state=RawEyeState.MID_BLINK,
        sharpness=8.5,
    )

    evaluated = ContextualFaceEvaluator.evaluate_face(obs)
    assert evaluated.raw_eye_score == -0.5
    assert evaluated.contextual_eye_score == -0.5
    assert evaluated.is_mid_blink_penalized is True
    assert evaluated.is_eyes_closed_ok is False


def test_kissing_exception_eyes_closed():
    """Valida que ojos cerrados durante un beso se eleven a 0.85 (Aceptable)."""
    obs = FaceObservation(
        face_id="F2",
        bbox=(0.2, 0.2, 0.4, 0.5),
        left_eye_state=RawEyeState.CLOSED,
        right_eye_state=RawEyeState.CLOSED,
        is_kissing_context=True,
        sharpness=9.2,
    )

    evaluated = ContextualFaceEvaluator.evaluate_face(obs)
    assert evaluated.raw_eye_score == 0.0
    assert evaluated.contextual_eye_score == 0.85  # Elevado por beso
    assert evaluated.is_eyes_closed_ok is True
    assert evaluated.focus_label == "Perfect Focus"


def test_looking_down_exception():
    """Valida que mirar hacia abajo con ojos cerrados se eleve a 0.80."""
    obs = FaceObservation(
        face_id="F3",
        bbox=(0.3, 0.1, 0.5, 0.4),
        left_eye_state=RawEyeState.CLOSED,
        right_eye_state=RawEyeState.CLOSED,
        head_pitch=28.0,  # Mirando hacia el ramo / suelo
        sharpness=7.5,
    )

    evaluated = ContextualFaceEvaluator.evaluate_face(obs)
    assert evaluated.raw_eye_score == 0.0
    assert evaluated.contextual_eye_score == 0.80  # Elevado por inclinación
    assert evaluated.is_eyes_closed_ok is True
    assert evaluated.focus_label == "Great Focus"


def test_laughing_squint_exception():
    """Valida que ojos achinados durante una carcajada se eleven a 0.85."""
    obs = FaceObservation(
        face_id="F4",
        bbox=(0.4, 0.2, 0.6, 0.5),
        left_eye_state=RawEyeState.CLOSED,
        right_eye_state=RawEyeState.CLOSED,
        smile_intensity=0.90,
        mouth_open=0.65,
        sharpness=8.0,
    )

    evaluated = ContextualFaceEvaluator.evaluate_face(obs)
    assert evaluated.contextual_eye_score == 0.85
    assert evaluated.is_eyes_closed_ok is True


def test_out_of_focus_tier():
    """Valida la clasificación de foco bajo."""
    obs = FaceObservation(
        face_id="F5",
        bbox=(0.1, 0.1, 0.2, 0.2),
        left_eye_state=RawEyeState.OPEN,
        right_eye_state=RawEyeState.OPEN,
        sharpness=0.8,
    )

    evaluated = ContextualFaceEvaluator.evaluate_face(obs)
    assert evaluated.focus_label == "Out of Focus"
    assert evaluated.focus_score == 0.8


if __name__ == "__main__":
    test_accidental_mid_blink_penalized()
    test_kissing_exception_eyes_closed()
    test_looking_down_exception()
    test_laughing_squint_exception()
    test_out_of_focus_tier()
    print("¡Todas las pruebas de evaluación facial pasaron exitosamente!")
