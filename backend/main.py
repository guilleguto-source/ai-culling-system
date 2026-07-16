"""
main.py — Punto de entrada del backend FastAPI para el sistema de Culling IA.
Expone endpoints REST consumidos por el proceso principal de Electron.
"""
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from services.settings_manager import load_settings, save_settings
from utils.hardware import get_hardware_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Culling Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado global del job de culling en curso
_job_state: dict[str, Any] = {
    "job_id": None,
    "status": "idle",        # idle | running | completed | error
    "progress": 0.0,
    "total": 0,
    "processed": 0,
    "results": [],
    "stats": {},
    "error": None,
}

# Cache de thumbnails en memoria (path → bytes)
_thumbnail_cache: dict[str, bytes] = {}


# --- Schemas ---

class IngestRequest(BaseModel):
    directory: str

class SettingsUpdateRequest(BaseModel):
    ratings_mapping: dict | None = None
    selection_preferences: dict | None = None
    culling_mode: str | None = None


# --- Endpoints de Sistema ---

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/hardware")
def hardware_info():
    """Retorna información del hardware detectado (GPU/CPU) para mostrar en la UI."""
    return get_hardware_info()


# --- Endpoints de Configuración ---

@app.get("/settings")
def get_settings():
    return load_settings()


@app.post("/settings")
def update_settings(data: SettingsUpdateRequest):
    current = load_settings()
    if data.ratings_mapping is not None:
        current["ratings_mapping"].update(data.ratings_mapping)
    if data.selection_preferences is not None:
        current["selection_preferences"].update(data.selection_preferences)
    if data.culling_mode is not None:
        current["culling_mode"] = data.culling_mode
    ok = save_settings(current)
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando la configuración")
    return {"success": True, "settings": current}


# --- Endpoints de Ingesta y Procesamiento ---

@app.post("/ingest")
def start_ingest(data: IngestRequest, background_tasks: BackgroundTasks):
    """Inicia el proceso de culling sobre un directorio de imágenes."""
    global _job_state

    if _job_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Ya hay un proceso de culling en curso")

    if not Path(data.directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directorio no válido: {data.directory}")

    job_id = f"job_{int(time.time())}"
    _job_state = {
        "job_id": job_id,
        "status": "running",
        "progress": 0.0,
        "total": 0,
        "processed": 0,
        "results": [],
        "stats": {},
        "error": None,
    }

    background_tasks.add_task(_run_culling_pipeline, data.directory, job_id)
    return {"job_id": job_id, "status": "started"}


@app.get("/status")
def get_status():
    """Retorna el estado actual del job de culling en progreso."""
    return {
        "job_id": _job_state["job_id"],
        "status": _job_state["status"],
        "progress": _job_state["progress"],
        "total": _job_state["total"],
        "processed": _job_state["processed"],
        "stats": _job_state["stats"],
        "error": _job_state["error"],
    }


@app.get("/results")
def get_results():
    """Retorna los resultados completos del último job completado."""
    if _job_state["status"] not in ("completed", "error"):
        raise HTTPException(status_code=400, detail="No hay resultados disponibles aún")
    return {
        "results": _job_state["results"],
        "stats": _job_state["stats"],
    }


@app.get("/thumbnail")
def get_thumbnail(path: str):
    """Retorna el thumbnail JPEG de una imagen por su ruta de archivo."""
    if path in _thumbnail_cache:
        return Response(content=_thumbnail_cache[path], media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Thumbnail no encontrado")


# --- Endpoint de Aprendizaje de Gustos ---

class LearnPreferenceRequest(BaseModel):
    winner_path: str
    loser_path: str

@app.post("/learn_preference")
def learn_preference(data: LearnPreferenceRequest):
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    from services.taste_model import taste_model
    from services import embedding_service

    def get_embedding(path_str):
        # Caché primero (poblado durante el culling); si no, decodifica y embebe.
        emb = embedding_service.embed_path(path_str, img_rgb=None)
        if emb is not None:
            return emb
        p = Path(path_str)
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        return embedding_service.embed_path(path_str, arr) if arr is not None else None

    learned = False
    if embedding_service.is_available():
        w_emb = get_embedding(data.winner_path)
        l_emb = get_embedding(data.loser_path)
        if w_emb is not None and l_emb is not None:
            event_dir = str(Path(data.winner_path).parent)
            taste_model.learn_preference(w_emb, l_emb, source="duel", event_dir=event_dir)
            learned = True
    if not learned:
        # Sin modelo CLIP el duelo no entrena, pero la elección del usuario
        # se respeta igual (re-export XMP abajo).
        logger.warning("Duelo sin aprendizaje: embeddings no disponibles.")

    # La elección del usuario manda: re-escribir el XMP de la ráfaga ahora mismo,
    # ascendiendo al ganador a "selected" y degradando al anterior a "duplicates".
    settings = load_settings()
    ratings_map = settings["ratings_mapping"]

    def _with_siblings(path_str: str) -> list[str]:
        # Incluye el RAW/JPG hermano (mismo stem) para mantener par RAW+JPG sincronizado.
        p = Path(path_str)
        out = [str(p)]
        if p.parent.is_dir():
            for sib in p.parent.glob(p.stem + ".*"):
                if sib != p and sib.suffix.lower() != p.suffix.lower():
                    out.append(str(sib))
        return out

    # Conservar el crop y la pre-edición del culling (snapshot del export)
    from services.export_snapshot import load_snapshot
    from services.preset_manager import load_preset
    snap = load_snapshot(str(Path(data.winner_path).parent))
    crops = snap.get("crops", {}) if snap else {}
    develops = snap.get("develops", {}) if snap else {}
    preset_path = snap.get("preset_path", "") if snap else ""
    preset_data = load_preset(preset_path) if preset_path and Path(preset_path).exists() else None

    rewrite = []
    for label in ("selected", "duplicates"):
        src = data.winner_path if label == "selected" else data.loser_path
        m = ratings_map.get(label, {})
        for path_str in _with_siblings(src):
            rewrite.append({
                "path": path_str,
                "label": label,
                "stars": m.get("stars", 0),
                "color": m.get("color", ""),
                "crop": crops.get(path_str),
                # La nueva ganadora hereda el develop de su hermana si no tenía
                "develop": develops.get(path_str) or (
                    develops.get(data.loser_path) if label == "selected" else None
                ),
            })

    from services.xmp_exporter import export_results_to_xmp
    from services.export_snapshot import update_labels
    xmp_stats = export_results_to_xmp(rewrite, ratings_map, overwrite=True,
                                      preset=preset_data)
    # Mantener el snapshot al día: el cambio vino de un duelo, no de Lightroom.
    update_labels(
        str(Path(data.winner_path).parent),
        {r["path"]: r["label"] for r in rewrite},
    )
    return {"success": True, "learned": learned, "xmp": xmp_stats}


# --- Endpoints de Presets (pre-edición) ---

class PresetUseRequest(BaseModel):
    path: str = ""   # "" = desactivar preset

@app.get("/presets")
def get_presets():
    pre = load_settings()["selection_preferences"].get("pre_edit", {})
    return {
        "active": pre.get("preset_path", ""),
        "recent": pre.get("recent_presets", []),
        "exposure_bias": pre.get("exposure_bias", 0.3),
        "enabled": pre.get("enabled", True),
    }

@app.post("/presets/use")
def use_preset(data: PresetUseRequest):
    settings = load_settings()
    pre = settings["selection_preferences"].setdefault("pre_edit", {})
    if not data.path:
        pre["preset_path"] = ""
        save_settings(settings)
        return {"success": True, "active": "", "recent": pre.get("recent_presets", [])}

    from services.preset_manager import load_preset, register_recent
    if not Path(data.path).exists():
        raise HTTPException(status_code=404, detail=f"No existe: {data.path}")
    if load_preset(data.path) is None:
        raise HTTPException(status_code=400, detail="No es un preset .xmp válido de Lightroom")
    pre_updated = register_recent(data.path)
    return {"success": True, "active": pre_updated["preset_path"],
            "recent": pre_updated["recent_presets"]}


# --- Endpoint de Sync desde Lightroom ---

class ReimportRequest(BaseModel):
    directory: str

@app.post("/reimport_xmp")
def reimport_xmp(data: ReimportRequest):
    """
    Relee los XMP de un directorio ya exportado y convierte las correcciones
    del usuario en Lightroom (subir/bajar estrellas) en ejemplos de
    entrenamiento: subió → +1, bajó → -1. Idempotente: un segundo sync sin
    cambios nuevos no genera ejemplos repetidos.
    """
    from services.export_snapshot import load_snapshot, update_synced_stars
    from services.xmp_reader import read_xmp
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    from services.taste_model import taste_model
    from services import embedding_service

    snapshot = load_snapshot(data.directory)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Este directorio no tiene un export previo")

    ratings_map = load_settings()["ratings_mapping"]
    synced = snapshot.get("synced_stars", {})

    # Agrupar RAW+JPG por (carpeta, stem) para no duplicar ejemplos del par.
    groups: dict[tuple, list[str]] = {}
    for path_str in snapshot["items"]:
        p = Path(path_str)
        groups.setdefault((str(p.parent).lower(), p.stem.lower()), []).append(path_str)

    def get_embedding(path_str):
        emb = embedding_service.embed_path(path_str, img_rgb=None)  # caché primero
        if emb is not None:
            return emb
        p = Path(path_str)
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        return embedding_service.embed_path(path_str, arr) if arr is not None else None

    upgraded = downgraded = 0
    learned = 0
    new_synced: dict[str, int] = {}
    emb_available = embedding_service.is_available()

    for members in groups.values():
        # Preferir el JPG para leer XMP y embeber (su caché ya existe del culling)
        members.sort(key=lambda s: Path(s).suffix.lower() in RAW_EXTENSIONS)
        primary = members[0]
        exported_label = snapshot["items"][primary]
        baseline = synced.get(primary, ratings_map.get(exported_label, {}).get("stars", 0))

        # El usuario pudo editar el JPG o el sidecar del RAW: primer XMP que difiera
        current = None
        for m in members:
            xmp = read_xmp(m)
            if xmp is not None and xmp["stars"] != baseline:
                current = xmp
                break
        if current is None:
            continue

        sign = +1 if current["stars"] > baseline else -1
        upgraded += sign > 0
        downgraded += sign < 0
        new_synced[primary] = current["stars"]

        if emb_available:
            emb = get_embedding(primary)
            if emb is not None:
                taste_model.add_example(emb, sign, "lightroom", event_dir=data.directory)
                learned += 1

    if new_synced:
        update_synced_stars(data.directory, new_synced)

    return {
        "success": True,
        "corrections": upgraded + downgraded,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "learned": learned,
        "embeddings_available": emb_available,
        "total_examples": taste_model.n_examples,
    }


# --- Endpoint de Apagado ---

@app.post("/shutdown")
def shutdown(background_tasks: BackgroundTasks):
    """Detiene el servidor backend de forma limpia."""
    def _do_shutdown():
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)
    background_tasks.add_task(_do_shutdown)
    return {"success": True}


# --- Pipeline de Culling (Background Task) ---

def _run_culling_pipeline(directory: str, job_id: str):
    """
    Ejecuta el pipeline completo de culling en segundo plano.
    Fases: Ingesta → Escena → Clustering → Calidad Técnica → Biométrica → Estética → Resultados
    """
    global _job_state, _thumbnail_cache

    try:
        settings = load_settings()
        prefs = settings["selection_preferences"]

        # Importaciones diferidas para no ralentizar el arranque del servidor
        from services.ingester import ingest_directory
        from services.scene_classifier import classify_scene, compute_saliency_region, SceneType
        from services.clustering import cluster_images, assign_cluster_representatives
        from services.cluster_gates import apply_technical_gates
        from services.auto_crop import propose_crop, detect_horizon_angle, LEVEL_LIMITS
        from services import pre_edit
        from services.preset_manager import load_preset
        from services.technical_quality import evaluate_technical_quality
        from services.aesthetic_assessment import evaluate_aesthetics_fast
        from services.taste_model import taste_model
        from services.settings_manager import get_blur_threshold, get_dbscan_epsilon
        import cv2

        blur_threshold = get_blur_threshold(settings)
        dbscan_epsilon = get_dbscan_epsilon(settings)

        # Inicializar detector de rostros YuNet
        # El modelo se carga desde la carpeta models/ relativa al script
        models_dir = Path(__file__).parent / "models"
        yunet_path = models_dir / "yunet.onnx"
        face_detector = None
        if yunet_path.exists():
            face_detector = cv2.FaceDetectorYN.create(
                str(yunet_path), "", (320, 320),
                score_threshold=0.6, nms_threshold=0.3, top_k=5000
            )

        # Modelo de estado de ojos (OCEC). Si falta, se usa el fallback EAR.
        eye_session = None
        eye_path = models_dir / "eye_state.onnx"
        if eye_path.exists():
            import onnxruntime as ort
            eye_session = ort.InferenceSession(str(eye_path), providers=["CPUExecutionProvider"])

        # FASE 1: Ingesta
        def progress_cb(done, total):
            _job_state["processed"] = done
            _job_state["total"] = total
            _job_state["progress"] = round(done / total * 40, 1)  # 0-40%

        records, ingest_stats = ingest_directory(directory, progress_callback=progress_cb)
        _thumbnail_cache = {r.path: r.thumb_ui for r in records if r.thumb_ui}
        _job_state["stats"]["ingest"] = ingest_stats

        # FASE 2: Clasificación de escena y análisis técnico
        from services.scene_classifier import classify_scene
        from services.face_assessment import evaluate_eyes_onnx, evaluate_eyes_fast, compute_face_sharpness
        scene_types, blur_scores, saliency_regions, aesthetic_scores = [], [], [], []
        blur_flags = []
        face_bboxes_list = []
        closed_flags = []           # ojos cerrados por imagen (solo retratos)
        face_sharpness_list = []    # nitidez Laplaciana por cara, por imagen
        eye_landmarks_list = []     # landmarks YuNet por imagen (para auto-crop)

        # Pre-edición: firmas de luz de TODAS las fotos (el consenso usa
        # también duplicadas/descartadas; solo se escribe en las selected)
        pre_edit_prefs = prefs.get("pre_edit", {})
        pre_edit_enabled = pre_edit_prefs.get("enabled", True)
        pre_skin, pre_global, pre_clip, pre_wb = [], [], [], []

        for i, record in enumerate(records):
            if record.error or record.thumb_ai is None:
                scene_types.append("detail")
                blur_scores.append(0.0)
                blur_flags.append(False)
                saliency_regions.append(None)
                face_bboxes_list.append([])
                closed_flags.append(False)
                face_sharpness_list.append([])
                eye_landmarks_list.append([])
                aesthetic_scores.append(0.5)
                pre_skin.append(None)
                pre_global.append(pre_edit.TARGET_MID)
                pre_clip.append(0.0)
                pre_wb.append(None)
                continue

            arr = record.thumb_ai

            # Clasificar escena (siempre que haya detector; la pref solo aplica a ojos)
            if face_detector is not None:
                scene_result = classify_scene(arr, face_detector)
                scene_type = scene_result.scene_type.value
                bboxes = scene_result.face_bboxes
                eye_lms = scene_result.eye_landmarks
            else:
                scene_type = "detail"
                bboxes = []
                eye_lms = []

            scene_types.append(scene_type)
            face_bboxes_list.append(bboxes)
            eye_landmarks_list.append(eye_lms)

            # Nitidez por cara (para el gate técnico dentro del cluster)
            face_sharpness_list.append(compute_face_sharpness(arr, bboxes) if bboxes else [])

            # Ojos cerrados (solo retratos, OCEC si está, EAR si no)
            closed = False
            if scene_type == "portrait" and eye_lms and prefs.get("detect_closed_eyes", True):
                fa = (evaluate_eyes_onnx(arr, eye_lms, eye_session) if eye_session is not None
                      else evaluate_eyes_fast(arr, eye_lms))
                closed = fa.any_closed_eyes
            closed_flags.append(closed)

            # Región de saliencia para detalles
            saliency = compute_saliency_region(arr) if scene_type == "detail" else None
            saliency_regions.append(saliency)

            # Análisis técnico
            tq = evaluate_technical_quality(arr, scene_type, bboxes, saliency, blur_threshold)
            blur_scores.append(tq.blur_score)
            blur_flags.append(tq.is_blurry)

            # Análisis estético heurístico (el gusto aprendido se aplica en el
            # ranking dentro del cluster, sobre embeddings — FASE 4)
            aesthetic_scores.append(evaluate_aesthetics_fast(arr))

            # Firma de luz (piel, global, quemados): también detecta basura
            # por exposición extrema, así que se mide siempre.
            skin_lum, global_lum, clip_frac = pre_edit.measure_luminance(arr, bboxes)
            pre_skin.append(skin_lum)
            pre_global.append(global_lum)
            pre_clip.append(clip_frac)
            pre_wb.append(pre_edit.estimate_wb(arr, bboxes) if pre_edit_enabled else None)

            _job_state["progress"] = 40.0 + round(i / len(records) * 30, 1)  # 40-70%

        # FASE 3: Clustering
        if prefs.get("detect_duplicates", True):
            clusters = cluster_images(
                [r.phash for r in records],
                [r.exif_datetime for r in records],
                scene_types,
                epsilon_hash=dbscan_epsilon,
            )
            clusters = assign_cluster_representatives(clusters, blur_scores, aesthetic_scores)
        else:
            # Sin agrupamiento: cada foto es su propio cluster
            from services.clustering import ImageCluster
            clusters = [
                ImageCluster(i, scene_types[i], [i], i)
                for i in range(len(records))
            ]

        # FASE 3b: Embeddings visuales (solo fotos en clusters con >1 imagen,
        # donde hay que desempatar). Caché en disco: re-correr un evento no
        # re-embebe. Si el modelo CLIP no está, se omite sin error.
        from services import embedding_service
        if embedding_service.is_available():
            multi_indices = [
                idx for c in clusters if len(c.image_indices) > 1
                for idx in c.image_indices
            ]
            embedded = 0
            for n, idx in enumerate(multi_indices):
                rec = records[idx]
                if rec.error or rec.thumb_ai is None:
                    continue
                if embedding_service.embed_path(rec.path, rec.thumb_ai) is not None:
                    embedded += 1
                _job_state["progress"] = 80.0 + round(n / max(1, len(multi_indices)) * 10, 1)  # 80-90%
            _job_state["stats"]["embeddings"] = {"computed": embedded, "candidates": len(multi_indices)}
            logger.info(f"Embeddings listos: {embedded}/{len(multi_indices)} fotos en clusters.")

        _job_state["progress"] = 90.0

        # FASE 3c: Pre-edición — sesiones de luz y ajustes por foto.
        # Analiza todas las fotos en orden temporal; se aplica solo a selected.
        develop_by_idx: dict[int, dict] = {}
        preset_data = None
        if pre_edit_enabled:
            preset_path = pre_edit_prefs.get("preset_path") or ""
            if preset_path and Path(preset_path).exists():
                preset_data = load_preset(preset_path)
            order = sorted(range(len(records)),
                           key=lambda i: (records[i].exif_datetime or "~", i))
            signatures = [
                pre_edit.PhotoSignature(
                    index=i,
                    has_people=bool(face_bboxes_list[i]),
                    wb=pre_wb[i],
                    skin_lum=pre_skin[i],
                    global_lum=pre_global[i],
                    clip_frac=pre_clip[i],
                ) for i in order
            ]
            develop_by_idx = pre_edit.compute_pre_edits(
                signatures,
                bias=float(pre_edit_prefs.get("exposure_bias", 0.3)),
                preset_wb_bias=preset_data.wb_bias if preset_data else (0.0, 0.0),
            )
            _job_state["stats"]["pre_edit"] = {
                "preset": preset_data.name if preset_data else None,
                "photos": len(develop_by_idx),
            }

        # FASE 4a: elegir representative por cluster y calcular su score
        ratings_map = settings["ratings_mapping"]
        auto_crop_level = prefs.get("auto_crop", "minimo")
        results = []

        SHARP_REF = 500.0   # ref para normalizar varianza Laplaciana (satura fotos nítidas)
        use_taste = taste_model.is_trained and embedding_service.is_available()
        rep_scores: dict[int, float] = {}
        singleton_reps: list[int] = []

        for cluster in clusters:
            if not cluster.image_indices:
                continue

            # Gates técnicos: el representative se elige solo entre las fotos
            # sin defectos técnicos relativos (ojos cerrados, cara borrosa),
            # si es que existe al menos una alternativa limpia en el cluster.
            candidates = apply_technical_gates(
                cluster.image_indices, closed_flags, face_sharpness_list
            )

            # Ranking entre candidatos:
            # - Con gusto entrenado (≥ MIN_EXAMPLES) → score del taste model
            #   sobre el embedding (los supervivientes ya son técnicamente OK).
            # - Fallback frío → combinado blur+heurísticas, ambos en 0..1.
            cluster_scores = []
            for idx in candidates:
                blur = blur_scores[idx] if idx < len(blur_scores) else 0.0
                aesthetic = aesthetic_scores[idx] if idx < len(aesthetic_scores) else 0.0
                blur_norm = min(1.0, blur / SHARP_REF)
                score = 0.6 * blur_norm + 0.4 * aesthetic
                if use_taste and len(candidates) > 1:
                    emb = embedding_service.embed_path(records[idx].path, records[idx].thumb_ai)
                    if emb is not None:
                        score = taste_model.predict_score(emb)
                cluster_scores.append((score, idx))

            cluster_scores.sort(key=lambda x: x[0])
            best_score, best_idx = cluster_scores[-1]
            cluster.representative_index = best_idx
            rep_scores[best_idx] = best_score
            if len(cluster.image_indices) == 1:
                singleton_reps.append(best_idx)

        # Basura real (label "blurry" → Roja/rechazada): SOLO las peores —
        # desenfoque severo (muy por debajo del umbral, no "algo blanda") o
        # exposición extrema (disparo al piso, lavada, casi negra). El blur
        # leve no se marca: solo penaliza el score y pierde duelos/poda.
        SEVERE_BLUR_FACTOR = 0.35
        trash_flags = [
            (blur_flags[i] and blur_scores[i] < blur_threshold * SEVERE_BLUR_FACTOR)
            or pre_edit.is_trash_exposure(pre_global[i], pre_clip[i])
            for i in range(len(records))
        ]

        # FASE 4b: Selectividad — barra de calidad final según el modo.
        # Los representatives de clusters >1 ganaron un duelo y son intocables;
        # la poda es SOLO entre singletons (fotos sueltas: transiciones,
        # relleno) rankeados por score. "few" = agresivo.
        KEEP_FRACTION = {"few": 0.40, "standard": 0.65, "more": 0.85}
        HIGHLIGHT_FRACTION = 0.10   # top-top (3★, no pueden faltar)

        def _selectable(idx: int) -> bool:
            if records[idx].error:
                return False
            if trash_flags[idx] and prefs.get("detect_blurry", True):
                return False
            return True

        pool = sorted((i for i in singleton_reps if _selectable(i)),
                      key=lambda i: rep_scores[i], reverse=True)
        keep_frac = KEEP_FRACTION.get(prefs.get("selectivity_target", "standard"), 0.65)
        keep_n = max(1, int(round(len(pool) * keep_frac))) if pool else 0
        demoted = set(pool[keep_n:])

        final_selected = sorted(
            (i for i in rep_scores if _selectable(i) and i not in demoted),
            key=lambda i: rep_scores[i], reverse=True)
        highlights: set[int] = set()
        if prefs.get("detect_highlights", True) and final_selected:
            top_n = max(1, int(round(len(final_selected) * HIGHLIGHT_FRACTION)))
            highlights = set(final_selected[:top_n])

        _job_state["stats"]["selectivity"] = {
            "mode": prefs.get("selectivity_target", "standard"),
            "singletons_demoted": len(demoted),
            "selected": len(final_selected),
            "highlighted": len(highlights),
        }

        # FASE 4c: Asignar calificaciones
        for cluster in clusters:
            if not cluster.image_indices:
                continue
            for idx in cluster.image_indices:
                if idx >= len(records):
                    continue
                record = records[idx]
                is_representative = (idx == cluster.representative_index)
                is_trash = trash_flags[idx] if idx < len(trash_flags) else False
                has_closed = closed_flags[idx] if idx < len(closed_flags) else False

                # Prioridad: error > basura > ojos cerrados > seleccionada > duplicado.
                # "blurry" (Roja/rechazada) es solo para basura real: desenfoque
                # severo o exposición extrema. El blur leve va por score.
                if record.error:
                    label = None
                    stars = 0
                elif is_trash and prefs.get("detect_blurry", True):
                    label = "blurry"
                    stars = ratings_map["blurry"]["stars"]
                elif has_closed and not is_representative:
                    label = "closed_eyes"
                    stars = ratings_map["closed_eyes"]["stars"]
                elif is_representative and idx in demoted:
                    # Singleton flojo podado por la barra de selectividad
                    label = "duplicates"
                    stars = ratings_map["duplicates"]["stars"]
                elif is_representative and idx in highlights:
                    label = "highlighted"
                    stars = ratings_map["highlighted"]["stars"]
                elif is_representative:
                    label = "selected"
                    stars = ratings_map["selected"]["stars"]
                else:
                    label = "duplicates"
                    stars = ratings_map["duplicates"]["stars"]

                # Auto-crop no destructivo: solo en las elegidas (crs:Crop* en XMP)
                crop_dict = None
                if (label in ("selected", "highlighted") and auto_crop_level in LEVEL_LIMITS
                        and record.thumb_ai is not None):
                    gray = cv2.cvtColor(record.thumb_ai, cv2.COLOR_RGB2GRAY)
                    prop = propose_crop(
                        scene_types[idx], face_bboxes_list[idx], eye_landmarks_list[idx],
                        saliency_regions[idx], record.thumb_ai.shape,
                        auto_crop_level, detect_horizon_angle(gray),
                    )
                    if prop is not None:
                        crop_dict = prop.to_dict()

                results.append({
                    "path": record.path,
                    "filename": record.filename,
                    "is_raw": record.is_raw,
                    "scene_type": scene_types[idx] if idx < len(scene_types) else "detail",
                    "cluster_id": cluster.cluster_id,
                    "is_cluster_representative": is_representative,
                    "label": label,
                    "stars": stars,
                    "color": ratings_map.get(label, {}).get("color", "") if label else "",
                    "blur_score": round(blur_scores[idx], 2) if idx < len(blur_scores) else 0,
                    "crop": crop_dict,
                    "has_crop": crop_dict is not None,
                    "develop": develop_by_idx.get(idx) if label in ("selected", "highlighted") else None,
                    "error": record.error,
                })
                
                # Si este JPG tenía un RAW emparejado, inyectar otra entrada en los resultados
                # para que también se escriba el metadato XMP sidecar para el RAW.
                if getattr(record, "linked_raw_path", None):
                    import copy
                    raw_res = copy.deepcopy(results[-1])
                    raw_res["path"] = record.linked_raw_path
                    raw_res["filename"] = Path(record.linked_raw_path).name
                    raw_res["is_raw"] = True
                    results.append(raw_res)

        # FASE 5: Exportar metadatos a XMP sidecars
        from services.xmp_exporter import export_results_to_xmp
        overwrite_xmp = prefs.get("overwrite_xmp_ratings", False)
        xmp_stats = export_results_to_xmp(results, ratings_map,
                                          overwrite=overwrite_xmp, preset=preset_data)
        _job_state["stats"]["xmp"] = xmp_stats

        # Persistir qué exportamos: base para el sync desde Lightroom
        # (las diferencias futuras en los XMP = correcciones del usuario).
        from services.export_snapshot import save_snapshot
        save_snapshot(directory, results,
                      preset_path=preset_data.path if preset_data else "")

        _job_state["results"] = results
        _job_state["status"] = "completed"
        _job_state["progress"] = 100.0
        _job_state["stats"]["total_clusters"] = len(clusters)
        _job_state["stats"]["total_images"] = len(records)

        logger.info(f"Job {job_id} completado: {len(results)} imágenes procesadas. XMP: {xmp_stats}")

    except Exception as e:
        logger.exception(f"Error en pipeline de culling: {e}")
        _job_state["status"] = "error"
        _job_state["error"] = str(e)
