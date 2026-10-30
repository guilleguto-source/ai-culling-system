"""
CullLab Contextual Facial & Eye Evaluator
Inspirado en la matriz de ponderación ocular y reglas de excepción de Narrative Select.
Evita falsos rechazos en besos, risa y poses mirando hacia abajo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class RawEyeState(str, Enum):
    OPEN = "open"
    PARTIALLY_OPEN = "partially_open"
    CLOSED = "closed"
    MID_BLINK = "mid_blink"           # Parpadeo accidental a medio cerrar
    GLASSES = "glasses"               # Lentes/gafas
    COVERED = "covered"               # Oculto por cabello/sombra


@dataclass
class FaceObservation:
    """Observación y métricas de un rostro individual detectado en la imagen."""
    face_id: str
    bbox: tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax) normalizado [0, 1]
    left_eye_state: RawEyeState
    right_eye_state: RawEyeState
    left_eye_ear: float = 0.30               # Eye Aspect Ratio [0, 1]
    right_eye_ear: float = 0.30
    head_pitch: float = 0.0                  # Inclinación vertical en grados (+ hacia abajo)
    head_yaw: float = 0.0                    # Giro horizontal en grados
    smile_intensity: float = 0.0             # [0, 1]
    mouth_open: float = 0.0                  # [0, 1]
    is_kissing_context: bool = False         # Detección de proximidad/contacto labial
    sharpness: float = 7.0                   # Nitidez focal en el rostro [0, 10]


@dataclass
class EvaluatedFace:
    """Rostro evaluado con scores normalizados y flags contextuales."""
    face_id: str
    raw_eye_score: float
    contextual_eye_score: float
    focus_score: float
    focus_label: str
    is_eyes_closed_ok: bool
    is_mid_blink_penalized: bool
    overall_quality: float                   # [0, 10]


class ContextualFaceEvaluator:
    """
    Evaluador contextual de calidad facial.
    Aplica excepciones de fotografía de bodas y retratos para erradicar falsos rechazos.
    """

    @classmethod
    def evaluate_face(cls, face: FaceObservation) -> EvaluatedFace:
        # 1. Ponderación base de cada ojo
        left_score = cls._score_single_eye(face.left_eye_state, face.left_eye_ear)
        right_score = cls._score_single_eye(face.right_eye_state, face.right_eye_ear)

        # Si uno parpadeó accidentalmente (mid-blink), penaliza todo el par
        is_mid_blink = (
            face.left_eye_state == RawEyeState.MID_BLINK
            or face.right_eye_state == RawEyeState.MID_BLINK
        )
        base_eye_score = -0.5 if is_mid_blink else min(left_score, right_score)

        # 2. Reglas de Excepción Contextual
        contextual_score = base_eye_score
        is_closed_ok = False

        # Excepción A: Beso
        if face.is_kissing_context:
            is_closed_ok = True
            contextual_score = max(contextual_score, 0.85)

        # Excepción B: Pose mirando hacia abajo (cabeza inclinada > 20°)
        elif face.head_pitch >= 20.0:
            is_closed_ok = True
            contextual_score = max(contextual_score, 0.80)

        # Excepción C: Risa efusiva (ojos achinados por sonrisa amplia)
        elif face.smile_intensity >= 0.75 and face.mouth_open >= 0.50:
            is_closed_ok = True
            contextual_score = max(contextual_score, 0.85)

        # 3. Clasificación de Foco (0 a 10)
        focus_val = max(0.0, min(10.0, face.sharpness))
        focus_label = cls._get_focus_label(focus_val)

        # 4. Calidad combinada del rostro [0, 10]
        # Escalar ojo de [-0.5, 1.0] a [0.0, 10.0]
        eye_norm = max(0.0, (contextual_score + 0.5) / 1.5) * 10.0
        overall = (focus_val * 0.60) + (eye_norm * 0.40)

        return EvaluatedFace(
            face_id=face.face_id,
            raw_eye_score=base_eye_score,
            contextual_eye_score=contextual_score,
            focus_score=focus_val,
            focus_label=focus_label,
            is_eyes_closed_ok=is_closed_ok,
            is_mid_blink_penalized=is_mid_blink,
            overall_quality=overall,
        )

    @staticmethod
    def _score_single_eye(state: RawEyeState, ear: float) -> float:
        if state == RawEyeState.OPEN:
            return 1.0
        if state == RawEyeState.GLASSES:
            return 1.0
        if state == RawEyeState.COVERED:
            return 0.5
        if state == RawEyeState.MID_BLINK:
            return -0.5
        if state == RawEyeState.PARTIALLY_OPEN:
            if ear >= 0.60:
                return 0.75
            if ear >= 0.25:
                return 0.50
            return 0.20
        # CLOSED
        return 0.0

    @staticmethod
    def _get_focus_label(focus: float) -> str:
        if focus > 9.0:
            return "Perfect Focus"
        if focus > 7.0:
            return "Great Focus"
        if focus > 5.0:
            return "Good Focus"
        if focus > 3.0:
            return "Soft Focus"
        if focus > 2.0:
            return "Very Soft"
        if focus > 1.0:
            return "Poor Focus"
        return "Out of Focus"
