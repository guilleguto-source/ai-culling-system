import logging
from dataclasses import dataclass, field
from typing import Any
import numpy as np
from services.ingester import ImageRecord
from services.scene_classifier import classify_scene, compute_saliency_region
from services.face_assessment import compute_face_sharpness
from services import face_mesh
from services.technical_quality import evaluate_technical_quality, max_region_sharpness
from services.aesthetic_assessment import evaluate_aesthetics_fast
from services.pre_edit import measure_luminance, estimate_wb, TARGET_MID

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
    face_count: int = 0                # lo que detectó YuNet (incluye basura)
    # MediaPipe confirma cuáles son caras de verdad: en una foto YuNet detectó
    # 43 "caras" (decoración) y solo 7 lo eran. valid_face_count es el conteo
    # fiable; los atributos solo se miden sobre esas.
    valid_face_count: int = 0
    looking_away_count: int = 0        # "caras viradas": no miran a cámara
    smiling_count: int = 0
    # Atributos POR cara (mismo orden que face_bboxes), serializable a JSON:
    # {valid, ear, blink, smile, gaze_out, yaw}. Necesario para elegir las
    # caras dudosas en la calibración y para entrenar sobre ellas.
    face_attrs: list = field(default_factory=list)
    # Embeddings de IDENTIDAD (ArcFace) por cara, mismo orden que face_bboxes.
    # NO se persiste en el caché de análisis (pesa y cambia poco el valor): en
    # una corrida con análisis cacheado queda vacío y la cobertura por persona
    # simplemente no actúa.
    face_identities: list = field(default_factory=list)
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

    # Atributos faciales (ojos / mirada / sonrisa) con MediaPipe sobre cada
    # recorte de cara. Reemplaza a eye_state.onnx, que era ruido sobre estas
    # fotos (97% de falsos "cerrado"). Si MediaPipe no está, no se marca nada.
    #
    # Se miden SIEMPRE (no dependen de `detect_closed_eyes`): el análisis
    # recoge hechos y la decisión aplica la política. Condicionarlo a la
    # preferencia dejaba a la calibración sin datos, y obligaba a re-analizar
    # el evento entero solo por activar la casilla. Cuesta ~47 ms/foto.
    analysis.face_count = len(analysis.face_bboxes)
    if analysis.face_bboxes and face_mesh.is_available():
        attrs = face_mesh.analyze_faces(arr, analysis.face_bboxes)
        validas = [a for a in attrs if a.valid]
        analysis.valid_face_count = len(validas)

        # Decisión de ojos por cara. Base: geometría de MediaPipe (eyes_closed).
        # Si hay un blink_detector.onnx dedicado (Fase 4), su probabilidad
        # refina la decisión — SIN mutar FaceAttributes: eyes_closed es un
        # property calculado y asignarle revienta con AttributeError.
        cerrada_por_cara = [a.valid and a.eyes_closed for a in attrs]
        from services import blink_classifier
        if blink_classifier.is_available():
            # OJO: cuando se incorpore un modelo real hay que subir
            # ANALYSIS_VERSION — cambia QUÉ se mide y el caché no lo distingue.
            onnx_probs = blink_classifier.predict_eyes_open(
                arr, analysis.face_bboxes, analysis.eye_landmarks)
            for i, a in enumerate(attrs):
                if not a.valid:
                    continue
                prob_abierto = onnx_probs[i] if i < len(onnx_probs) else 0.5
                prob_intencional = 0.0 if a.looking_away else 1.0  # heurística simple
                score = prob_abierto * 0.7 + prob_intencional * 0.3
                cerrada_por_cara[i] = score < 0.45

        # Serializar DESPUÉS de decidir: persiste la decisión por cara
        # (closed_hybrid) junto a las señales crudas. Antes se serializaba
        # arriba del bloque y la "persistencia" del híbrido no persistía nada.
        analysis.face_attrs = [
            {**face_mesh.to_dict(a), "closed_hybrid": bool(cerrada_por_cara[i])}
            for i, a in enumerate(attrs)
        ]
        analysis.closed_eyes_count = sum(
            1 for i, a in enumerate(attrs) if a.valid and cerrada_por_cara[i])
        analysis.looking_away_count = sum(1 for a in validas if a.looking_away)
        analysis.smiling_count = sum(1 for a in validas if a.smiling)
        analysis.any_closed_eyes = analysis.closed_eyes_count > 0

    # Identidad de las personas (ArcFace). Guardado: si el modelo no está, no
    # hace nada. Alinea por los 5 landmarks de YuNet cuando existen.
    from services import face_identity
    if analysis.face_bboxes and face_identity.is_available():
        analysis.face_identities = [
            face_identity.embed_face(
                arr, bbox,
                landmarks=analysis.eye_landmarks[i] if i < len(analysis.eye_landmarks) else None)
            for i, bbox in enumerate(analysis.face_bboxes)
        ]

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
    analysis.aesthetic_score = evaluate_aesthetics_fast(arr)

    # Firma de luz (pre-edición)
    skin_lum, global_lum, clip_frac = measure_luminance(arr, analysis.face_bboxes)
    analysis.pre_skin_lum = skin_lum
    analysis.pre_global_lum = global_lum
    analysis.pre_clip_frac = clip_frac
    if pre_edit_enabled:
        analysis.pre_wb = estimate_wb(arr, analysis.face_bboxes)

    return analysis
