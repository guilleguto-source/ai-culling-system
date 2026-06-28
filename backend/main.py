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
        from services.technical_quality import evaluate_technical_quality
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
        from services.face_assessment import evaluate_eyes_onnx, evaluate_eyes_fast
        scene_types, blur_scores, saliency_regions = [], [], []
        blur_flags = []
        face_bboxes_list = []
        closed_flags = []           # ojos cerrados por imagen (solo retratos)

        for i, record in enumerate(records):
            if record.error or record.thumb_ai is None:
                scene_types.append("detail")
                blur_scores.append(0.0)
                blur_flags.append(False)
                saliency_regions.append(None)
                face_bboxes_list.append([])
                closed_flags.append(False)
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

            _job_state["progress"] = 40.0 + round(i / len(records) * 30, 1)  # 40-70%

        # FASE 3: Clustering
        aesthetic_scores = [0.5] * len(records)  # Placeholder hasta tener modelo estético

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

        _job_state["progress"] = 80.0

        # FASE 4: Asignar calificaciones
        ratings_map = settings["ratings_mapping"]
        results = []

        for cluster in clusters:
            if not cluster.image_indices:
                continue

            # Score combinado, ambos términos en 0..1 (antes mezclaba varianza cruda
            # con aesthetic*100, dominado por el blur).
            SHARP_REF = 500.0   # ref para normalizar varianza Laplaciana (satura fotos nítidas)
            cluster_scores = []
            for idx in cluster.image_indices:
                blur = blur_scores[idx] if idx < len(blur_scores) else 0.0
                aesthetic = aesthetic_scores[idx] if idx < len(aesthetic_scores) else 0.0
                blur_norm = min(1.0, blur / SHARP_REF)
                score = 0.6 * blur_norm + 0.4 * aesthetic
                cluster_scores.append((score, idx))

            # Sort ascending (worst to best)
            cluster_scores.sort(key=lambda x: x[0])
            sorted_indices = [x[1] for x in cluster_scores]

            best_idx = sorted_indices[-1]
            cluster.representative_index = best_idx

            for idx in cluster.image_indices:
                if idx >= len(records):
                    continue
                record = records[idx]
                is_representative = (idx == cluster.representative_index)
                is_blurry = blur_flags[idx] if idx < len(blur_flags) else False
                has_closed = closed_flags[idx] if idx < len(closed_flags) else False

                # Prioridad: error > borrosa > ojos cerrados > seleccionada > duplicado.
                # (Las no-mejores de una ráfaga ya NO se etiquetan "blurry" si son nítidas;
                #  van a "duplicates". Los ojos cerrados tienen su propia etiqueta.)
                if record.error:
                    label = None
                    stars = 0
                elif is_blurry and prefs.get("detect_blurry", True):
                    label = "blurry"
                    stars = ratings_map["blurry"]["stars"]
                elif has_closed and not is_representative:
                    label = "closed_eyes"
                    stars = ratings_map["closed_eyes"]["stars"]
                elif is_representative:
                    label = "selected"
                    stars = ratings_map["selected"]["stars"]
                else:
                    label = "duplicates"
                    stars = ratings_map["duplicates"]["stars"]

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
                    "error": record.error,
                })

        # FASE 5: Exportar metadatos a XMP sidecars
        from services.xmp_exporter import export_results_to_xmp
        overwrite_xmp = prefs.get("overwrite_xmp_ratings", False)
        xmp_stats = export_results_to_xmp(results, ratings_map, overwrite=overwrite_xmp)
        _job_state["stats"]["xmp"] = xmp_stats

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
