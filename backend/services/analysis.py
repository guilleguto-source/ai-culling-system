import logging
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from services.ingester import ImageRecord
from services.scene_classifier import classify_scene, compute_saliency_region
from services.face_assessment import compute_face_sharpness
from services.technical_quality import evaluate_technical_quality, max_region_sharpness
from services.aesthetic_assessment import evaluate_aesthetics_fast, evaluate_aesthetics_detailed
from services.pre_edit import measure_luminance, estimate_wb, TARGET_MID
from services import tonal_rescue

logger = logging.getLogger("analysis")

@dataclass
class PhotoAnalysis:
    index: int
    path: str
    # mtime del archivo con el que se guardó este análisis. Lo rellena el store
    # al leer del caché; sirve como clave del embedding cacheado sin re-stat del
    # disco (crítico con el NAS). 0.0 en un análisis recién calculado en memoria.
    mtime: float = 0.0
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
    face_count: int = 0                # Detectado por UniFace/SCRFD
    # UniFace aplica NMS y threshold de confianza, así que valid_face_count
    # coincide con face_count salvo bordes de confianza por debajo del umbral.
    valid_face_count: int = 0
    looking_away_count: int = 0        # "caras viradas": no miran a cámara
    smiling_count: int = 0
    # Atributos POR cara (mismo orden que face_bboxes), serializable a JSON:
    # {valid, ear, blink, smile, gaze_out, yaw}. Necesario para elegir las
    # caras dudosas en la calibración y para entrenar sobre ellas.
    face_attrs: list = field(default_factory=list)
    # Embeddings de IDENTIDAD (ArcFace) por cara, mismo orden que face_bboxes.
    # Persistido en SQLite para garantizar cobertura VIP y consistencia de personas en caché.
    face_identities: list = field(default_factory=list)
    phash: str = ""
    exif_datetime: str = ""
    
    blur_score: float = 0.0
    blur_flag: bool = False
    sharp_anywhere: float = 0.0
    aesthetic_score: float = 0.5
    aesthetic_breakdown: dict = field(default_factory=dict)
    saliency_region: Any = None
    
    pre_skin_lum: float | None = None
    pre_global_lum: float = TARGET_MID
    pre_clip_frac: float = 0.0
    pre_wb: tuple[float, float] | None = None
    tonal_adjustments: dict = field(default_factory=dict)
    
    error: str = ""

def analyze_photo(
    index: int,
    record: ImageRecord,
    face_detector: Any,
    eye_session: Any,
    blur_threshold: float,
    detect_closed_eyes: bool,
    pre_edit_enabled: bool,
    gaze_estimator: Any = None,
) -> PhotoAnalysis:
    """Realiza el análisis técnico y semántico completo de una imagen."""
    analysis = PhotoAnalysis(index=index, path=record.path)

    if record.error or record.thumb_ai is None:
        analysis.error = "Error previo o falta thumb_ai"
        return analysis

    arr = record.thumb_ai

    # Clasificar escena y detectar rostros
    if face_detector is not None:
        scene_result = classify_scene(arr, face_detector, gaze_estimator=gaze_estimator)
        analysis.scene_type = scene_result.scene_type.value
        analysis.face_bboxes = scene_result.face_bboxes
        analysis.eye_landmarks = scene_result.eye_landmarks
        # Los embeddings (ArcFace) ya vienen listos desde UniFace
        analysis.face_identities = scene_result.face_embeddings
        face_yaws = scene_result.face_yaws
        face_pitches = scene_result.face_pitches
    else:
        analysis.scene_type = "detail"
        analysis.face_bboxes = []
        analysis.eye_landmarks = []
        analysis.face_identities = []
        face_yaws = []
        face_pitches = []

    # Nitidez por cara
    if analysis.face_bboxes:
        analysis.face_sharpness = compute_face_sharpness(arr, analysis.face_bboxes)
    else:
        analysis.face_sharpness = []

    # Rellenar con metadatos de ingesta si se computa de cero
    analysis.phash = record.phash
    analysis.exif_datetime = record.exif_datetime

    analysis.face_count = len(analysis.face_bboxes)
    
    CROWD_THRESHOLD = 8

    if analysis.face_bboxes:
        analysis.valid_face_count = analysis.face_count
        
        if analysis.face_count >= CROWD_THRESHOLD:
            analysis.any_closed_eyes = False
            analysis.closed_eyes_count = 0
            for i in range(analysis.face_count):
                yaw = float(face_yaws[i]) if i < len(face_yaws) else 0.0
                analysis.face_attrs.append({
                    "valid": True,
                    "eyes_closed": False,
                    "ear": 1.0,
                    "smile": False,
                    "gaze_out": bool(abs(yaw) > 35.0),
                    "yaw": yaw
                })
        else:
            # Evaluar estado de ojos con el método rápido de parche (EAR)
            from services.face_assessment import evaluate_eyes_fast
            eye_result = evaluate_eyes_fast(arr, analysis.eye_landmarks, analysis.face_bboxes)
            
            analysis.any_closed_eyes = bool(eye_result.any_closed_eyes)
            analysis.closed_eyes_count = int(sum(1 for f in eye_result.face_results if f.has_closed_eyes))
            
            # Mapear los resultados a face_attrs
            for i, f_res in enumerate(eye_result.face_results):
                yaw = float(face_yaws[i]) if i < len(face_yaws) else 0.0
                analysis.face_attrs.append({
                    "valid": True,
                    "eyes_closed": bool(f_res.has_closed_eyes),
                    "ear": float(f_res.eye_aspect_ratio),
                    "smile": False,
                    "gaze_out": bool(abs(yaw) > 35.0),
                    "yaw": yaw
                })

        analysis.looking_away_count = sum(1 for a in analysis.face_attrs if a.get("gaze_out", False))
    else:
        analysis.valid_face_count = 0
        analysis.any_closed_eyes = False
        analysis.closed_eyes_count = 0
        analysis.looking_away_count = 0
        pass

    # Identidad de las personas (ArcFace).
    # Las identidades ya se cargaron desde UniFace. No necesitamos face_identity.py.
    pass

    # Saliencia para detalles
    if analysis.scene_type == "detail":
        analysis.saliency_region = compute_saliency_region(arr)

    # Análisis técnico (desenfoque)
    tq = evaluate_technical_quality(
        arr, 
        analysis.scene_type, 
        analysis.face_bboxes, 
        analysis.saliency_region, 
        blur_threshold,
        iso=record.iso,
    )
    analysis.blur_score = tq.blur_score
    analysis.blur_flag = tq.is_blurry
    analysis.sharp_anywhere = max_region_sharpness(arr) if tq.is_blurry else tq.blur_score

    # Análisis estético
    breakdown = evaluate_aesthetics_detailed(arr)
    analysis.aesthetic_score = breakdown.overall_score
    analysis.aesthetic_breakdown = breakdown.to_dict()

    # Firma de luz (pre-edición)
    skin_lum, global_lum, clip_frac = measure_luminance(arr, analysis.face_bboxes)
    analysis.pre_skin_lum = skin_lum
    analysis.pre_global_lum = global_lum
    analysis.pre_clip_frac = clip_frac
    if pre_edit_enabled:
        analysis.pre_wb = estimate_wb(arr, analysis.face_bboxes)

    # Rescate tonal (altas luces y sombras - Fase 3)
    if pre_edit_enabled:
        tonal_rep = tonal_rescue.analyze_tonal_range(arr, analysis.face_bboxes)
        analysis.tonal_adjustments = tonal_rescue.suggest_tonal_adjustments(tonal_rep)

    return analysis
