import logging
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from services.ingester import ImageRecord
from services.scene_classifier import classify_scene, compute_saliency_region
from services.face_assessment import evaluate_eyes_onnx, evaluate_eyes_fast, compute_face_sharpness
from services.technical_quality import evaluate_technical_quality, max_region_sharpness
from services.aesthetic_assessment import evaluate_aesthetics_fast
from services.pre_edit import measure_luminance, estimate_wb, TARGET_MID

logger = logging.getLogger("analysis")

@dataclass
class PhotoAnalysis:
    index: int
    path: str
    scene_type: str = "detail"
    face_bboxes: list = field(default_factory=list)
    eye_landmarks: list = field(default_factory=list)
    face_sharpness: list = field(default_factory=list)
    any_closed_eyes: bool = False
    # En una grupal casi siempre HAY alguien con los ojos cerrados (6 ojos x
    # ~20% de parpadeo = 70% de las fotos). Por eso el conteo importa más que
    # el booleano: la comparación útil es RELATIVA dentro de la ráfaga
    # (la peor del grupo), no absoluta.
    closed_eyes_count: int = 0
    face_count: int = 0
    phash: str = ""
    exif_datetime: str = ""
    
    blur_score: float = 0.0
    blur_flag: bool = False
    sharp_anywhere: float = 0.0
    aesthetic_score: float = 0.5
    saliency_region: Any = None
    
    pre_skin_lum: float | None = None
    pre_global_lum: float = TARGET_MID
    pre_clip_frac: float = 0.0
    pre_wb: tuple[float, float] | None = None
    
    error: str = ""

def analyze_photo(
    index: int,
    record: ImageRecord,
    face_detector: Any,
    eye_session: Any,
    blur_threshold: float,
    detect_closed_eyes: bool,
    pre_edit_enabled: bool,
) -> PhotoAnalysis:
    """Realiza el análisis técnico y semántico completo de una imagen."""
    analysis = PhotoAnalysis(index=index, path=record.path)

    if record.error or record.thumb_ai is None:
        analysis.error = "Error previo o falta thumb_ai"
        return analysis

    arr = record.thumb_ai

    # Clasificar escena y detectar rostros
    if face_detector is not None:
        scene_result = classify_scene(arr, face_detector)
        analysis.scene_type = scene_result.scene_type.value
        analysis.face_bboxes = scene_result.face_bboxes
        analysis.eye_landmarks = scene_result.eye_landmarks
    else:
        analysis.scene_type = "detail"
        analysis.face_bboxes = []
        analysis.eye_landmarks = []

    # Nitidez por cara
    if analysis.face_bboxes:
        analysis.face_sharpness = compute_face_sharpness(arr, analysis.face_bboxes)
    else:
        analysis.face_sharpness = []

    # Rellenar con metadatos de ingesta si se computa de cero
    analysis.phash = record.phash
    analysis.exif_datetime = record.exif_datetime

    # Ojos cerrados
    analysis.face_count = len(analysis.face_bboxes)
    if analysis.scene_type == "portrait" and analysis.eye_landmarks and detect_closed_eyes:
        fa = (evaluate_eyes_onnx(arr, analysis.eye_landmarks, eye_session) if eye_session is not None
              else evaluate_eyes_fast(arr, analysis.eye_landmarks))
        analysis.any_closed_eyes = fa.any_closed_eyes
        analysis.closed_eyes_count = sum(1 for f in fa.face_results if f.has_closed_eyes)

    # Saliencia para detalles
    if analysis.scene_type == "detail":
        analysis.saliency_region = compute_saliency_region(arr)

    # Análisis técnico (desenfoque)
    tq = evaluate_technical_quality(arr, analysis.scene_type, analysis.face_bboxes, analysis.saliency_region, blur_threshold)
    analysis.blur_score = tq.blur_score
    analysis.blur_flag = tq.is_blurry
    analysis.sharp_anywhere = max_region_sharpness(arr) if tq.is_blurry else tq.blur_score

    # Análisis estético
    analysis.aesthetic_score = evaluate_aesthetics_fast(arr)

    # Firma de luz (pre-edición)
    skin_lum, global_lum, clip_frac = measure_luminance(arr, analysis.face_bboxes)
    analysis.pre_skin_lum = skin_lum
    analysis.pre_global_lum = global_lum
    analysis.pre_clip_frac = clip_frac
    if pre_edit_enabled:
        analysis.pre_wb = estimate_wb(arr, analysis.face_bboxes)

    return analysis
