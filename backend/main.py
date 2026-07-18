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

import numpy as np

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

@app.on_event("startup")
def startup_event():
    from services.thumbnail_store import auto_cleanup_cache
    try:
        auto_cleanup_cache(30)
        logger.info("Caché de miniaturas de más de 30 días limpiada de forma automática.")
    except Exception as e:
        logger.error(f"Error en auto-limpieza de caché: {e}")

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
_thumbnail_duel_cache: dict[str, bytes] = {}


# --- Schemas ---

class IngestRequest(BaseModel):
    directory: str
    mode: str = "cull_edit"   # "cull" (solo selección) | "cull_edit" (selección + edición)

class SettingsUpdateRequest(BaseModel):
    ratings_mapping: dict | None = None
    selection_preferences: dict | None = None


# --- Endpoints de Sistema ---

def _code_stamp() -> float:
    """mtime más reciente del código del backend (main.py + services/*.py)."""
    base = Path(__file__).parent
    stamps = [os.path.getmtime(base / "main.py")]
    stamps += [os.path.getmtime(p) for p in (base / "services").glob("*.py")]
    return max(stamps)

# Se fija al ARRANCAR: si luego el código en disco cambia, este proceso quedó
# desactualizado. Nos pasó 3 veces: el usuario re-corre el culling tras un fix
# y el backend viejo en memoria sirve lógica anterior sin que nadie lo note.
_LOADED_CODE_STAMP = _code_stamp()


@app.get("/health")
def health_check():
    try:
        stale = _code_stamp() > _LOADED_CODE_STAMP
    except OSError:
        stale = False
    return {"status": "ok", "version": "1.0.0", "stale_code": stale}


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
    ok = save_settings(current)
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando la configuración")
    return {"success": True, "settings": current}


# --- Endpoints de Ingesta y Procesamiento ---

def _start_pipeline_job(data: IngestRequest, background_tasks: BackgroundTasks, mode: str):
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

    _job_state["mode"] = mode
    background_tasks.add_task(_run_culling_pipeline, data.directory, job_id, mode)
    return {"job_id": job_id, "status": "started", "mode": mode}

@app.post("/cull")
def start_culling(request: IngestRequest, background_tasks: BackgroundTasks):
    """Inicia un trabajo de culling en segundo plano."""
    return _start_pipeline_job(request, background_tasks, "cull")

@app.post("/reselect")
def start_reselect(request: IngestRequest, background_tasks: BackgroundTasks):
    """Re-evalúa selectividad (Fase C) usando la caché de análisis (instantáneo)."""
    return _start_pipeline_job(request, background_tasks, "cull")

@app.post("/ingest")
def start_ingest(data: IngestRequest, background_tasks: BackgroundTasks):
    """Inicia el proceso de culling sobre un directorio de imágenes."""
    return _start_pipeline_job(data, background_tasks, data.mode)




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

@app.get("/debug/overlay")
def get_debug_overlay(path: str):
    """Retorna la imagen con overlays de depuración dibujados en OpenCV (Fase F)."""
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
    # Cargar imagen física en tamaño AI
    p = Path(path)
    from services.ingester import _extract_raw_preview, _load_jpg, THUMB_AI_SIZE, RAW_EXTENSIONS
    from PIL import Image
    import numpy as np
    try:
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        if arr is None:
            raise HTTPException(status_code=400, detail="No se pudo cargar la imagen")
        img_pil = Image.fromarray(arr)
        img_pil.thumbnail(THUMB_AI_SIZE, Image.LANCZOS)
        img_rgb = np.array(img_pil)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando imagen: {e}")
        
    # Intentar cargar análisis de DB
    from services.analysis_store import init_store, load_analysis
    conn = init_store(str(p.parent))
    current_mtime = os.path.getmtime(path)
    analysis = load_analysis(conn, path, current_mtime)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="El análisis no está en base de datos. Escanee la carpeta primero.")
        
    import cv2
    from services.debug_overlay import draw_debug_overlay
    img_res = draw_debug_overlay(img_rgb, analysis)
    
    # Codificar a WebP
    _, encoded = cv2.imencode(".webp", cv2.cvtColor(img_res, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_WEBP_QUALITY, 85])
    return Response(content=encoded.tobytes(), media_type="image/webp")


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
def get_thumbnail(path: str, size: str = "ui"):
    """Retorna el thumbnail WebP de una imagen por su ruta de archivo y tamaño (Fase E/Disco)."""
    from services.thumbnail_store import read_thumbnail_from_disk
    data = read_thumbnail_from_disk(path, size)
    if data:
        return Response(content=data, media_type="image/webp")
        
    # Fallback por si la caché en RAM tiene algo (compatibilidad / desarrollo)
    if size == "duel" and path in _thumbnail_duel_cache:
        return Response(content=_thumbnail_duel_cache[path], media_type="image/webp")
    if path in _thumbnail_cache:
        return Response(content=_thumbnail_cache[path], media_type="image/webp")
        
    raise HTTPException(status_code=404, detail="Thumbnail no encontrado")

@app.get("/cache/projects")
def get_cached_projects():
    """Retorna una lista de proyectos con caché de miniaturas y análisis en disco."""
    import sqlite3
    db_dir = Path("backend/models/analysis")
    if not db_dir.exists():
        return []
        
    projects = []
    from services.thumbnail_store import CACHE_ROOT
    
    for db_path in db_dir.glob("*.db"):
        if db_path.name == "taste_examples.db":
            continue
            
        mtime = db_path.stat().st_mtime
        size = db_path.stat().st_size
        
        directory = ""
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT path FROM photo_analysis LIMIT 1")
            row = cursor.fetchone()
            if row:
                directory = str(Path(row[0]).parent)
            conn.close()
        except Exception:
            pass
            
        if not directory:
            continue
            
        dir_hash = db_path.stem
        proj_cache_dir = CACHE_ROOT / dir_hash
        if proj_cache_dir.exists():
            for root, _, files in os.walk(proj_cache_dir):
                for f in files:
                    size += os.path.getsize(os.path.join(root, f))
                    
        size_mb = round(size / (1024 * 1024), 2)
        
        projects.append({
            "directory": directory,
            "last_accessed": mtime,
            "size_mb": size_mb,
            "db_hash": dir_hash
        })
        
    projects.sort(key=lambda p: p["last_accessed"], reverse=True)
    return projects

@app.post("/cache/open")
def open_cache_folder():
    """Abre la carpeta del caché de miniaturas en el explorador de Windows."""
    import os
    from services.thumbnail_store import CACHE_ROOT
    if not CACHE_ROOT.exists():
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(CACHE_ROOT))
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo abrir la carpeta: {e}")

class ClearCacheRequest(BaseModel):
    directory: str

@app.post("/cache/clear")
def clear_cache(request: ClearCacheRequest):
    """Borra manualmente la caché de miniaturas y la base de datos de un proyecto."""
    from services.thumbnail_store import clear_project_cache
    from services.analysis_store import _get_db_path
    
    # 1. Borrar miniaturas
    clear_project_cache(request.directory)
    
    # 2. Borrar base de datos de análisis
    db_path = _get_db_path(request.directory)
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception as e:
            logger.error(f"Error al borrar DB de análisis en limpieza manual: {e}")
            
    return {"success": True}


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
    # En modo "solo culling" la edición aún no se aplicó: el duelo re-escribe
    # solo labels; crop/develop llegarán con /apply_edits.
    edits_on = bool(snap and snap.get("edits_applied", True))
    crops = snap.get("crops", {}) if snap and edits_on else {}
    develops = snap.get("develops", {}) if snap and edits_on else {}
    preset_path = snap.get("preset_path", "") if snap and edits_on else ""
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


# --- Endpoints de Calibración (Fase G2) ---

class LabelRequest(BaseModel):
    photo_path: str
    face_index: int
    face_bbox: list = []
    labels: dict          # {"eyes": "abiertos", "gaze": "camara", ...}
    predictions: dict = {} # lo que propuso el detector (para medir acuerdo)

@app.get("/calibration/candidates")
def calibration_candidates(directory: str, limit: int = 30):
    """Caras pendientes de calibrar, las más dudosas primero."""
    from services.calibration import candidates
    from services.calibration_store import ATTRIBUTES, CalibrationStore
    if not Path(directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directorio no válido: {directory}")
    cands = candidates(directory, limit=limit)
    store = CalibrationStore()
    return {
        "atributos": ATTRIBUTES,
        "etiquetadas": store.count(),
        "candidatas": [
            {"photo_path": c.photo_path, "face_index": c.face_index,
             "face_bbox": c.face_bbox, "uncertainty": c.uncertainty,
             "predictions": c.predictions}
            for c in cands
        ],
    }

@app.get("/calibration/face")
def calibration_face(path: str, x: int, y: int, w: int, h: int):
    """Recorte de una cara para mostrar en la vista de calibración."""
    from services.calibration import crop_face
    jpeg = crop_face(path, [x, y, w, h], mark=True)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="No se pudo recortar la cara")
    return Response(content=jpeg, media_type="image/jpeg")

@app.post("/calibration/label")
def calibration_label(data: LabelRequest):
    """Guarda la verdad de campo del fotógrafo para una cara."""
    from services.calibration import face_embedding
    from services.calibration_store import CalibrationStore, ATTRIBUTES
    from services import face_mesh
    from services.analysis_store import init_store, load_analysis

    store = CalibrationStore()
    # Embedding y geometría se calculan una vez por cara y se reutilizan en
    # todos los atributos: juntos forman el vector híbrido que entrena G3.
    emb = face_embedding(data.photo_path, data.face_bbox) if data.face_bbox else None
    feats = None
    try:
        directory = str(Path(data.photo_path).parent)
        a = load_analysis(init_store(directory), data.photo_path,
                          os.path.getmtime(data.photo_path))
        if a and 0 <= data.face_index < len(a.face_attrs):
            feats = face_mesh.feature_vector(face_mesh.from_dict(a.face_attrs[data.face_index]))
    except Exception:
        feats = None   # sin geometría: la fila se rellena luego con backfill

    guardadas = 0
    for attribute, value in data.labels.items():
        if attribute not in ATTRIBUTES or value not in ATTRIBUTES[attribute]:
            continue
        store.add_label(
            photo_path=data.photo_path, face_index=data.face_index,
            attribute=attribute, value=value,
            predicted=data.predictions.get(attribute, ""),
            face_bbox=data.face_bbox, embedding=emb, features=feats,
        )
        guardadas += 1

    # Hay etiquetas nuevas: el clasificador aprendido debe re-entrenarse
    from services.face_classifier import face_classifier
    face_classifier.invalidate()
    return {"success": True, "guardadas": guardadas, "total": store.count()}

@app.get("/calibration/stats")
def calibration_stats():
    """
    Precisión REAL sobre las fotos del usuario: la de la geometría (G1) medida
    contra sus etiquetas, y la del clasificador aprendido (G3) en validación
    cruzada. Así se ve con números cuál conviene para cada atributo.
    """
    from services.calibration_store import CalibrationStore, ATTRIBUTES
    from services.face_classifier import face_classifier, MIN_EXAMPLES
    from services.calibration import backfill_features

    store = CalibrationStore()
    # Rellenar la geometría de etiquetas viejas (una sola vez) para que cuenten
    # en el entrenamiento híbrido. Barato tras la primera pasada.
    if backfill_features(store):
        face_classifier.invalidate()

    out = {}
    for at in ATTRIBUTES:
        geo = store.agreement(at)
        aprendido = face_classifier.cross_val_accuracy(at)
        out[at] = {
            **geo,
            "geometria": geo["precision"],
            "aprendido": aprendido,
            "faltan": max(0, MIN_EXAMPLES - store.count(at)),
        }
    return {"total": store.count(), "por_atributo": out}


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


# --- Endpoint de Aplicar Edición (tras revisar la selección) ---

class ApplyEditsRequest(BaseModel):
    directory: str

@app.post("/apply_edits")
def apply_edits(data: ApplyEditsRequest):
    """
    Escribe la edición propuesta (crop + preset + WB + exposición) en las
    fotos actualmente selected/highlighted del snapshot — instantáneo, sin
    re-analizar. Respeta los duelos hechos después del culling (el snapshot
    se actualiza con cada 'Elegir esta').
    """
    from services.export_snapshot import load_snapshot, set_edits_applied
    from services.preset_manager import load_preset
    from services.xmp_exporter import export_results_to_xmp

    snap = load_snapshot(data.directory)
    if snap is None:
        raise HTTPException(status_code=404, detail="Este directorio no tiene un culling previo")

    ratings_map = load_settings()["ratings_mapping"]
    crops = snap.get("crops", {})
    develops = snap.get("develops", {})
    preset_path = snap.get("preset_path", "")
    preset_data = load_preset(preset_path) if preset_path and Path(preset_path).exists() else None

    rewrite = []
    for path_str, label in snap["items"].items():
        if label not in ("selected", "highlighted"):
            continue
        m = ratings_map.get(label, {})
        rewrite.append({
            "path": path_str,
            "label": label,
            "stars": m.get("stars", 0),
            "color": m.get("color", ""),
            "crop": crops.get(path_str),
            "develop": develops.get(path_str),
        })

    if not rewrite:
        raise HTTPException(status_code=400, detail="No hay fotos seleccionadas en el snapshot")

    xmp_stats = export_results_to_xmp(rewrite, ratings_map, overwrite=True, preset=preset_data)
    set_edits_applied(data.directory)

    # El export cambió el mtime de las fotos: re-sellar el análisis para no
    # invalidar el caché (los píxeles no cambiaron, solo los metadatos).
    from services.analysis_store import init_store, refresh_mtimes
    try:
        refresh_mtimes(init_store(data.directory), [r["path"] for r in rewrite])
    except Exception as e:
        logger.warning(f"No se pudo re-sellar el análisis tras aplicar edición: {e}")

    return {
        "success": True,
        "edited": len(rewrite),
        "preset": preset_data.name if preset_data else None,
        "xmp": xmp_stats,
    }


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

    from services.scene_grouping import nearest_scene

    upgraded = downgraded = 0
    learned = 0
    new_synced: dict[str, int] = {}
    keepers: list[dict] = []          # para aprender revelado/recorte (estilo)
    emb_available = embedding_service.is_available()

    for members in groups.values():
        # Preferir el JPG para leer XMP y embeber (su caché ya existe del culling)
        members.sort(key=lambda s: Path(s).suffix.lower() in RAW_EXTENSIONS)
        primary = members[0]
        exported_label = snapshot["items"][primary]
        baseline = synced.get(primary, ratings_map.get(exported_label, {}).get("stars", 0))

        # Leer el XMP COMPLETO (rating + revelado + recorte) de cada miembro.
        # El usuario pudo editar el JPG o el sidecar del RAW.
        xmps = {m: read_xmp(m, full=True) for m in members}
        # Gusto: primer XMP cuyo rating difiere del baseline.
        current = next((x for x in xmps.values() if x and x["stars"] != baseline), None)
        # Estilo: el XMP que trae los ajustes (revelado/recorte).
        edited = (next((x for x in xmps.values() if x and (x.get("develop") or x.get("crop"))), None)
                  or next((x for x in xmps.values() if x), None))
        stars_now = edited["stars"] if edited else baseline

        # El embedding se calcula una vez y se reutiliza (gusto + escena).
        emb = get_embedding(primary) if emb_available and (current or stars_now >= 2) else None

        # 1) GUSTO: solo si cambió el rating (un cambio es la señal).
        if current is not None:
            sign = +1 if current["stars"] > baseline else -1
            upgraded += sign > 0
            downgraded += sign < 0
            new_synced[primary] = current["stars"]
            if emb is not None:
                taste_model.add_example(emb, sign, "lightroom", event_dir=data.directory)
                learned += 1

        # 2) ESTILO: revelado/recorte de las keepers (2★+), tengan o no cambio
        #    de rating — su edición es el estilo a aprender.
        if edited is not None and stars_now >= 2 and (edited.get("develop") or edited.get("crop")):
            keepers.append({
                "path": primary, "rating": stars_now,
                "develop": edited.get("develop", {}), "crop": edited.get("crop", {}),
                "scene": nearest_scene(emb) or "",
            })

    if new_synced:
        update_synced_stars(data.directory, new_synced)

    # Aprender revelado + recorte de las keepers de este evento (re-aprende las
    # recetas por escena incluyendo estas fotos).
    from services.sync_learning import learn_styles_from_event
    estilo = learn_styles_from_event(keepers)

    from services.export_snapshot import mark_synced
    mark_synced(data.directory)

    total_corrections = upgraded + downgraded
    return {
        "success": True,
        "corrections": total_corrections,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "learned": learned,
        "embeddings_available": emb_available,
        "total_examples": taste_model.n_examples,
        "estilo_aprendido": estilo,   # revelado/recorte: keepers guardadas + escenas
        # Cero correcciones casi siempre significa que Lightroom no volcó los
        # cambios al archivo: viven en su catálogo, no en el XMP que leemos.
        "hint": ("¿Guardaste los metadatos en Lightroom? En Lightroom: "
                 "Metadatos → Guardar metadatos en archivo (Ctrl+S), o activa "
                 "'Escribir cambios automáticamente en XMP'.")
                if total_corrections == 0 else "",
    }


class CatalogDiffRequest(BaseModel):
    directory: str
    catalog_path: str
    since: str = "2025-02-01"
    limit: int | None = None


@app.post("/lightroom/pending_changes")
def lightroom_pending_changes(data: CatalogDiffRequest):
    """
    Fase R: avisa si Lightroom tiene cambios que aún no se volcaron al archivo
    (el caso en que un sync no encontraría nada que aprender).
    """
    from services.catalog_diff import find_pending_changes, mensaje_para_usuario
    if not Path(data.catalog_path).exists():
        raise HTTPException(status_code=404, detail="No se encontró el catálogo")
    res = find_pending_changes(data.catalog_path, data.directory, data.since, data.limit)
    return {**res, "mensaje": mensaje_para_usuario(res)}


class UndoRequest(BaseModel):
    directory: str


@app.post("/undo_export")
def undo_export(data: UndoRequest):
    """
    Fase O: deshace el último export, devolviendo cada foto al XMP que tenía
    antes (respaldo byte a byte tomado justo antes de escribir).
    """
    from services.undo_export import restore_previous_state, has_backup
    if not has_backup(data.directory):
        raise HTTPException(status_code=404,
                            detail="No hay respaldo previo para este directorio")
    return restore_previous_state(data.directory)


@app.get("/undo_export/available")
def undo_available(directory: str):
    from services.undo_export import has_backup
    return {"disponible": has_backup(directory)}


class SyncReminderRequest(BaseModel):
    directory: str
    hours: float = 8.0


class HistoryBootstrapRequest(BaseModel):
    catalog_path: str = ""   # .lrcat; si vacío, usar `root` (XMP en disco)
    root: str = ""
    since: str = "2025-02-01"
    dry_run: bool = True


@app.post("/history/bootstrap")
def history_bootstrap(data: HistoryBootstrapRequest):
    """
    Fase H1: etiquetar el historial (catálogo Lightroom o XMP) según la
    convención de rating del usuario. dry_run=True solo reporta qué saldría.
    """
    from services.history_bootstrap import bootstrap_from_catalog, bootstrap_from_xmp
    if data.catalog_path:
        return bootstrap_from_catalog(data.catalog_path, data.since, data.dry_run)
    if data.root:
        return bootstrap_from_xmp(data.root, data.since, data.dry_run)
    raise HTTPException(status_code=400, detail="Indica catalog_path o root")


class HistoryScenesRequest(BaseModel):
    k: int = 10
    label: str = "positive"
    limit: int | None = None


@app.post("/history/embed")
def history_embed(data: HistoryScenesRequest):
    """Fase I (lote pesado): calcula/cachea los embeddings CLIP del historial."""
    from services.scene_grouping import embed_history
    return embed_history(label=data.label, limit=data.limit)


@app.post("/history/scenes")
def history_scenes(data: HistoryScenesRequest):
    """Fase I: agrupa por escena las fotos ya embebidas y persiste la categoría."""
    from services.scene_grouping import assign_scenes
    return assign_scenes(k=data.k, label=data.label)


@app.post("/history/feed-taste")
def history_feed_taste(data: HistoryScenesRequest):
    """Fase H2: alimenta el taste model con positivas (+1) y negativas (-1)."""
    from services.history_taste import feed_taste_from_history
    return feed_taste_from_history(limit=data.limit)


@app.post("/history/feed-taste-pairs")
def history_feed_taste_pairs():
    """
    Fase Q: alimenta el gusto con pares ganadora/perdedora DENTRO de cada
    ráfaga revisada. Compara alternativas parecidas, que es la tarea real.
    """
    from services.history_taste import feed_pairwise_from_history
    return feed_pairwise_from_history()


@app.post("/history/develop-style")
def history_develop_style():
    """Fase J: aprende el 'look' (contraste, tono, color) por escena."""
    from services.develop_style import learn_recipes
    recipes = learn_recipes()
    return {"escenas_con_receta": len(recipes),
            "recetas": {s: {k: v for k, v in r.items()} for s, r in recipes.items()}}


@app.post("/history/crop-style")
def history_crop_style():
    """Fase K: aprende tendencias de recorte (área, encuadre, ángulo) por escena."""
    from services.crop_style import learn_crop_style
    estilos = learn_crop_style()
    return {"escenas_con_estilo": len(estilos), "estilos": estilos}


@app.get("/sync/pending")
def sync_pending():
    """Eventos culleados que toca recordar sincronizar desde Lightroom."""
    from services.export_snapshot import pending_reminders
    return {"events": pending_reminders()}


@app.post("/sync/snooze")
def sync_snooze(data: SyncReminderRequest):
    """Posponer el recordatorio de un evento (p.ej. 8 h)."""
    from services.export_snapshot import snooze_reminder
    snooze_reminder(data.directory, data.hours)
    return {"success": True}


@app.post("/sync/dismiss")
def sync_dismiss(data: SyncReminderRequest):
    """Apagar el recordatorio de un evento ('ya terminé')."""
    from services.export_snapshot import dismiss_reminder
    dismiss_reminder(data.directory)
    return {"success": True}


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

def _run_culling_pipeline(directory: str, job_id: str, mode: str = "cull_edit"):
    """
    Ejecuta el pipeline completo de culling en segundo plano.
    Fases: Ingesta → Escena → Clustering → Calidad Técnica → Biométrica → Estética → Resultados

    mode="cull": las propuestas de edición (crop + revelado) se CALCULAN y
    quedan en el snapshot, pero NO se escriben en los XMP — el usuario revisa
    la selección y luego las aplica con POST /apply_edits (instantáneo).
    """
    global _job_state, _thumbnail_cache

    try:
        settings = load_settings()
        prefs = settings["selection_preferences"]

        # Importaciones diferidas para no ralentizar el arranque del servidor
        from services.ingester import ingest_directory
        from services.scene_classifier import classify_scene, compute_saliency_region, SceneType
        from services.clustering import cluster_images, assign_cluster_representatives
        from services.cluster_gates import apply_technical_gates_explained
        from services.auto_crop import propose_crop, detect_horizon_angle, LEVEL_LIMITS
        from services import pre_edit
        from services.preset_manager import load_preset
        from services.technical_quality import evaluate_technical_quality, max_region_sharpness
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

        # FASE 1 & 2: Ingesta y análisis técnico / semántico por lotes
        from services.ingester import get_ingest_tasks, process_single_image
        from services.analysis import analyze_photo, PhotoAnalysis
        from services.analysis_store import init_store, load_analysis, save_analysis
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import os
        import time

        t0_ingest = time.time()
        tasks = get_ingest_tasks(directory)
        total = len(tasks)
        
        # Inicializar cachés globales
        global _thumbnail_cache, _thumbnail_duel_cache
        _thumbnail_cache.clear()
        _thumbnail_duel_cache.clear()

        pre_edit_prefs = prefs.get("pre_edit", {})
        pre_edit_enabled = pre_edit_prefs.get("enabled", True)

        records = []
        analyses: list[PhotoAnalysis] = []
        conn = init_store(directory)

        BATCH_SIZE = 200
        errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch_tasks = tasks[batch_start:batch_start + BATCH_SIZE]
            batch_records = []

            # Verificar si están en la caché de análisis SQLite y tienen miniaturas en disco
            from services.thumbnail_store import get_thumbnail_cache_paths
            to_process = []
            
            for path, linked_raw in batch_tasks:
                current_mtime = os.path.getmtime(path)
                ans = load_analysis(conn, str(path), current_mtime)
                ui_path, duel_path = get_thumbnail_cache_paths(str(path))
                if ans and ui_path.exists() and duel_path.exists():
                    from services.ingester import ImageRecord, RAW_EXTENSIONS
                    rec = ImageRecord(
                        path=str(path),
                        filename=path.name,
                        is_raw=path.suffix.lower() in RAW_EXTENSIONS,
                        linked_raw_path=linked_raw,
                        phash=ans.phash,
                        exif_datetime=ans.exif_datetime
                    )
                    batch_records.append(rec)
                else:
                    to_process.append((path, linked_raw))

            # Ingestar lote de forma concurrente solo para lo que no esté en caché
            if to_process:
                with ThreadPoolExecutor(max_workers=None) as executor:
                    futures = {executor.submit(process_single_image, p, lr): p for p, lr in to_process}
                    for future in as_completed(futures):
                        rec = future.result()
                        batch_records.append(rec)
                        if rec.error:
                            errors += 1

            # El orden de as_completed no es determinista, ordenamos por path
            batch_records.sort(key=lambda r: r.path)

            # Analizar el lote e ir liberando memoria
            for record in batch_records:
                global_idx = len(records)
                
                current_mtime = os.path.getmtime(record.path) if not record.error else 0.0
                ans = load_analysis(conn, record.path, current_mtime)
                
                if record.error:
                    ans = analyze_photo(global_idx, record, face_detector, eye_session, blur_threshold, prefs.get("detect_closed_eyes", True), pre_edit_enabled)
                    analyses.append(ans)
                    records.append(record)
                    continue

                if not ans:
                    # Si no está en DB (se procesó en este paso)
                    ans = analyze_photo(
                        index=global_idx,
                        record=record,
                        face_detector=face_detector,
                        eye_session=eye_session,
                        blur_threshold=blur_threshold,
                        detect_closed_eyes=prefs.get("detect_closed_eyes", True),
                        pre_edit_enabled=pre_edit_enabled,
                    )
                    save_analysis(conn, ans, current_mtime)
                else:
                    ans.index = global_idx

                # Liberar RAM pesada: el array numpy del lote procesado ya no se necesita en RAM
                record.thumb_ai = None

                analyses.append(ans)
                records.append(record)

                _job_state["processed"] = len(records)
                _job_state["total"] = total
                _job_state["progress"] = round(len(records) / total * 70, 1)  # 0-70% combinados!

        elapsed = time.time() - t0_ingest
        _job_state["stats"]["ingest"] = {
            "total": total,
            "success": total - errors,
            "errors": errors,
            "elapsed_seconds": round(elapsed, 1),
            "images_per_second": round(total / elapsed, 1) if elapsed > 0 else 0,
        }

        # G3: sobre los conteos por-cara que ya midió la geometría, aplicar el
        # clasificador aprendido de tu calibración donde ya es fiable. Antes del
        # clustering: los gates y la decisión leen estos conteos. No toca la DB
        # (queda G1 crudo cacheado) para reflejar siempre la última calibración.
        from services.face_classifier import refine_face_counts
        refinadas = refine_face_counts(analyses)
        if refinadas:
            _job_state["stats"]["face_learned"] = {"fotos_ajustadas": refinadas}
            logger.info(f"G3 (calibración) ajustó los conteos de cara en {refinadas} fotos.")

        # FASE 3: Clustering
        if prefs.get("detect_duplicates", True):
            clusters = cluster_images(
                [r.phash for r in records],
                [r.exif_datetime for r in records],
                [a.scene_type for a in analyses],
                epsilon_hash=dbscan_epsilon,
            )
            clusters = assign_cluster_representatives(clusters, [a.blur_score for a in analyses], [a.aesthetic_score for a in analyses])
        else:
            # Sin agrupamiento: cada foto es su propio cluster
            from services.clustering import ImageCluster
            clusters = [
                ImageCluster(i, analyses[i].scene_type, [i], i)
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
                if rec.error:
                    continue
                
                # Recargar temporalmente thumb_ai desde disco para calcular embedding
                thumb_ai = None
                from services.ingester import _extract_raw_preview, _load_jpg, THUMB_AI_SIZE
                from PIL import Image
                try:
                    p = Path(rec.path)
                    arr = _extract_raw_preview(p) if rec.is_raw else _load_jpg(p)
                    if arr is not None:
                        img = Image.fromarray(arr)
                        img.thumbnail(THUMB_AI_SIZE, Image.LANCZOS)
                        thumb_ai = np.array(img)
                except Exception as e:
                    logger.error(f"Error recargando thumb_ai temporal para embedding: {e}")

                if thumb_ai is not None:
                    if embedding_service.embed_path(rec.path, thumb_ai) is not None:
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
                    has_people=bool(analyses[i].face_bboxes),
                    wb=analyses[i].pre_wb,
                    skin_lum=analyses[i].pre_skin_lum,
                    global_lum=analyses[i].pre_global_lum,
                    clip_frac=analyses[i].pre_clip_frac,
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

            # Fase J: fusionar el "look" aprendido por escena. Guardado:
            # setdefault (nunca pisa exposición/WB de pre_edit), embedding
            # solo-caché (sin recargar) y no-op si no hay recetas. Se aplica
            # a las fotos que ya tienen embedding; crece al cachearse más.
            from services.develop_style import load_recipes, style_for_scene
            from services.scene_grouping import nearest_scene
            from services import embedding_service as _emb_svc
            recipes = load_recipes()
            if recipes and _emb_svc.is_available():
                aplicadas = 0
                for i in develop_by_idx:
                    emb = _emb_svc.embed_path(records[i].path, None)
                    estilo = style_for_scene(nearest_scene(emb), recipes) if emb is not None else {}
                    for k, v in estilo.items():
                        develop_by_idx[i].setdefault(k, v)
                    aplicadas += bool(estilo)
                _job_state["stats"]["develop_style"] = {"fotos": aplicadas}

        # FASE 4a: elegir representative por cluster y calcular su score
        ratings_map = settings["ratings_mapping"]
        auto_crop_level = prefs.get("auto_crop", "minimo")
        results = []

        SHARP_REF = 500.0   # ref para normalizar varianza Laplaciana (satura fotos nítidas)
        use_taste = taste_model.is_trained and embedding_service.is_available()
        rep_scores: dict[int, float] = {}
        all_scores: dict[int, float] = {}   # score de TODAS las fotos: ordena el duelo
        gate_reasons: dict[int, str] = {}   # por qué cayó cada descartada por gate
        decidido_por: dict[int, str] = {}   # gate | gusto | score (para no mentir)

        for cluster in clusters:
            if not cluster.image_indices:
                continue

            # Gates técnicos: el representative se elige solo entre las fotos
            # sin defectos técnicos relativos (ojos cerrados, cara borrosa),
            # si es que existe al menos una alternativa limpia en el cluster.
            candidates, motivos_gate = apply_technical_gates_explained(
                cluster.image_indices,
                [a.any_closed_eyes for a in analyses],
                [a.face_sharpness for a in analyses]
            )
            gate_reasons.update(motivos_gate)

            # Ranking:
            # - Con gusto entrenado (≥ MIN_EXAMPLES) → score del taste model
            #   sobre el embedding.
            # - Fallback frío → combinado blur+heurísticas, ambos en 0..1.
            # Se puntúa el cluster ENTERO, no solo los supervivientes: el duelo
            # muestra también a los gateados y necesita ordenarlos.
            for idx in cluster.image_indices:
                a = analyses[idx]
                blur_norm = min(1.0, a.blur_score / SHARP_REF)
                score = 0.6 * blur_norm + 0.4 * a.aesthetic_score
                if use_taste and len(cluster.image_indices) > 1:
                    emb = embedding_service.embed_path(records[idx].path, records[idx].thumb_ai)
                    if emb is not None:
                        score = taste_model.predict_score(emb)
                all_scores[idx] = score

            # El representative sale solo de los que pasaron los gates.
            best_idx = max(candidates, key=lambda i: all_scores[i])
            cluster.representative_index = best_idx
            rep_scores[best_idx] = all_scores[best_idx]

            # QUIÉN decidió: si los gates dejaron una sola candidata, ganó por
            # el gate, NO por score (afirmar "mejor score" ahí sería falso).
            if len(cluster.image_indices) > 1:
                if len(candidates) == 1 and motivos_gate:
                    decidido_por[best_idx] = "gate"
                elif use_taste:
                    decidido_por[best_idx] = "gusto"
                else:
                    decidido_por[best_idx] = "score"

        # Basura real (label "blurry" → Roja/rechazada): SOLO las peores —
        # desenfoque severo (muy por debajo del umbral, no "algo blanda") o
        # exposición extrema (disparo al piso, lavada, casi negra). El blur
        # leve no se marca: solo penaliza el score y pierde duelos/poda.
        # Enfoque selectivo: si el mejor bloque del cuadro es nítido, los
        # rostros suaves son una decisión del fotógrafo (ramo, anillos), no
        # un error — nunca basura.
        SEVERE_BLUR_FACTOR = 0.35
        trash_flags = [
            (a.blur_flag
             and a.blur_score < blur_threshold * SEVERE_BLUR_FACTOR
             and a.sharp_anywhere < blur_threshold)
            or pre_edit.is_trash_exposure(a.pre_global_lum, a.pre_clip_frac)
            for a in analyses
        ]

        # FASE 4b & 4c: Selectividad y Calificaciones
        from services.decision import apply_decision_logic
        results, demoted, final_selected, highlights = apply_decision_logic(
            records=records,
            analyses=analyses,
            clusters=clusters,
            rep_scores=rep_scores,
            all_scores=all_scores,
            gate_reasons=gate_reasons,
            decided_by=decidido_por,
            trash_flags=trash_flags,
            prefs=prefs,
            settings=settings,
            develop_by_idx=develop_by_idx
        )

        _job_state["stats"]["selectivity"] = {
            "mode": prefs.get("selectivity_target", "standard"),
            "singletons_demoted": len(demoted),
            "selected": len(final_selected),
            "highlighted": len(highlights),
        }

        # FASE 4d: cobertura por persona (ArcFace). Garantiza que cada identidad
        # del evento tenga al menos una foto seleccionada — el dolor real del
        # fotógrafo de eventos ("me olvidé de la abuela"). Solo PROMUEVE: nunca
        # baja nada. No-op si falta el modelo o si el análisis vino de caché.
        if prefs.get("ensure_person_coverage", True):
            from services.face_identity import group_event_identities
            from services.decision import photos_for_coverage

            embs_por_foto = {
                a.index: a.face_identities for a in analyses if a.face_identities
            }
            if embs_por_foto:
                identidades = group_event_identities(embs_por_foto)
                promovidas = photos_for_coverage(
                    identidades, set(final_selected), all_scores)
                por_path = {r["path"]: r for r in results}
                aplicadas = 0
                for idx in promovidas:
                    if idx >= len(records):
                        continue
                    r = por_path.get(records[idx].path)
                    if r and r["label"] not in ("selected", "highlighted"):
                        r["label"] = "selected"
                        r["stars"] = ratings_map.get("selected", {}).get("stars", 4)
                        r["color"] = ratings_map.get("selected", {}).get("color", "")
                        r["reasons"] = ["✔ Única buena de esta persona en el evento"]
                        aplicadas += 1
                _job_state["stats"]["person_coverage"] = {
                    "identidades": len({i for ids in identidades.values() for i in ids}),
                    "promovidas": aplicadas,
                }

        # FASE 5: Exportar metadatos a XMP sidecars
        # Antes de tocar UN SOLO archivo, respaldar el XMP actual de todas las
        # fotos. Si el respaldo falla, se aborta: nunca escribimos sin red.
        from services.undo_export import capture_previous_state
        backup_stats = capture_previous_state(
            directory, [r["path"] for r in results if not r.get("error")])
        _job_state["stats"]["backup"] = backup_stats

        from services.xmp_exporter import export_results_to_xmp
        overwrite_xmp = prefs.get("overwrite_xmp_ratings", False)
        if mode == "cull":
            # Solo selección: labels/estrellas/banderines sí; edición NO
            # (queda propuesta en el snapshot para /apply_edits).
            to_export = [{**r, "crop": None, "develop": None} for r in results]
            xmp_stats = export_results_to_xmp(to_export, ratings_map,
                                              overwrite=overwrite_xmp)
        else:
            xmp_stats = export_results_to_xmp(results, ratings_map,
                                              overwrite=overwrite_xmp, preset=preset_data)
        _job_state["stats"]["xmp"] = xmp_stats
        _job_state["stats"]["edits_applied"] = (mode != "cull")

        # Escribir el XMP dentro del JPG cambia su mtime, lo que invalidaría el
        # análisis que acabamos de guardar (el caché nunca acertaría y la
        # re-selección re-analizaría todo). Los píxeles no cambiaron: se
        # re-sella el análisis con el mtime nuevo.
        from services.analysis_store import refresh_mtimes
        resellados = refresh_mtimes(conn, [r["path"] for r in results])
        logger.info(f"Análisis re-sellado tras el export XMP: {resellados} fotos.")

        # Persistir qué exportamos: base para el sync desde Lightroom
        # (las diferencias futuras en los XMP = correcciones del usuario).
        from services.export_snapshot import save_snapshot
        save_snapshot(directory, results,
                      preset_path=preset_data.path if preset_data else "",
                      edits_applied=(mode != "cull"))

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
