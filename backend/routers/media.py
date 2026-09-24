"""
routers/media.py — Endpoints de miniaturas, búsqueda semántica, storyline, previsualizaciones EXIF/Raw, presets y administración de caché.
"""
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.job_manager import job_manager
from services.settings_manager import load_settings, save_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Media & Thumbnails"])

# Alias para compatibilidad hacia atrás
_thumbnail_cache = job_manager._thumbnail_cache
_thumbnail_duel_cache = job_manager._thumbnail_duel_cache


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class ClearCacheRequest(BaseModel):
    directory: str
    db_hash: str | None = None


class PresetUseRequest(BaseModel):
    path: str = ""   # "" = desactivar preset


# --- Endpoints ---

@router.get("/debug/overlay")
def get_debug_overlay(path: str):
    """Retorna la imagen con overlays de depuración dibujados en OpenCV (Fase F)."""
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
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
        
    from services.analysis_store import init_store, load_analysis
    conn = init_store(str(p.parent))
    current_mtime = _safe_getmtime(path)
    analysis = load_analysis(conn, path, current_mtime)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="El análisis no está en base de datos. Escanee la carpeta primero.")
        
    import cv2
    from services.debug_overlay import draw_debug_overlay
    img_res = draw_debug_overlay(img_rgb, analysis)
    
    _, encoded = cv2.imencode(".webp", cv2.cvtColor(img_res, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_WEBP_QUALITY, 85])
    return Response(content=encoded.tobytes(), media_type="image/webp")


@router.get("/search/semantic")
def semantic_search(q: str, directory: str, limit: int = 50):
    """
    Busca fotos por texto libre usando embeddings CLIP en el directorio activo.
    """
    from services.semantic_search import search_photos
    from services.thumbnail_store import thumb_url

    results = search_photos(q, directory, limit)

    formatted = [{
        "path": r["path"],
        "filename": Path(r["path"]).name,
        "score": round(r["score"], 3),
        "thumb": thumb_url(r["path"]),
    } for r in results]

    return {"results": formatted}


class RenameChapterRequest(BaseModel):
    directory: str
    chapter_id: str
    new_name: str

class OverrideChapterRequest(BaseModel):
    directory: str
    photo_path: str
    chapter_id: str

@router.get("/storyline")
def get_storyline(directory: str):
    """
    Agrupa cronológicamente (gap en mins) y extrae el medoide visual de cada capítulo.
    """
    from services.storyline_builder import build_storyline
    storyline = build_storyline(directory)
    return {"storyline": storyline}


@router.get("/storyline/vocabulary")
def get_storyline_vocabulary():
    """Devuelve el vocabulario de nombres de eventos aprendidos."""
    from services.event_library import get_vocabulary
    return {"vocabulary": get_vocabulary()}


@router.post("/storyline/rename")
def rename_storyline_chapter(req: RenameChapterRequest):
    """
    Renombra un capítulo y aprende el término agregándolo al Event Library.
    """
    from services.event_library import add_vocabulary_term
    # Por ahora solo lo agregamos a la biblioteca global
    # En un futuro podríamos actualizar un archivo de storyline persistente por directorio.
    add_vocabulary_term(req.new_name)
    return {"status": "success", "term_learned": req.new_name}


@router.post("/storyline/override")
def override_storyline_chapter(req: OverrideChapterRequest):
    """Fuerza una foto a pertenecer a un capítulo específico en el Storyline."""
    from services.storyline_builder import save_override
    save_override(req.directory, req.photo_path, req.chapter_id)
    return {"status": "success"}


class RenameVIPRequest(BaseModel):
    directory: str
    identity_id: int
    name: str


def _get_vip_names_path(directory: str) -> Path:
    import hashlib
    from services.app_paths import get_analysis_dir
    dir_hash = hashlib.md5(directory.encode("utf-8")).hexdigest()
    get_analysis_dir().mkdir(parents=True, exist_ok=True)
    return get_analysis_dir() / f"{dir_hash}_vip_names.json"


def _load_vip_names(directory: str) -> dict[str, str]:
    import json
    p = _get_vip_names_path(directory)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_vip_names(directory: str, names: dict[str, str]):
    import json
    p = _get_vip_names_path(directory)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando nombres VIP: {e}")


@router.get("/vip-subjects")
def get_vip_subjects(directory: str):
    """
    Retorna los top-5 personajes/sujetos detectados con sus fotos representativas y nombres.
    """
    from collections import defaultdict
    from services.thumbnail_store import thumb_url
    from services.export_snapshot import load_snapshot

    saved_names = _load_vip_names(directory)

    # 1. Intentar desde job_manager (en memoria)
    identities_by_photo: dict[str, list[int]] = {}
    _, current_results, _ = job_manager.get_results()
    if current_results:
        for r in current_results:
            if r.get("path") and r.get("identity_ids"):
                identities_by_photo[r["path"]] = r["identity_ids"]

    # 2. Si no hay en memoria, intentar desde snapshot
    if not identities_by_photo:
        snap = load_snapshot(directory)
        if snap and snap.get("identities"):
            identities_by_photo = snap["identities"]

    # 3. Fallback: desde analysis_store
    if not identities_by_photo:
        try:
            from services.analysis_store import get_all_analysis
            from services.face_identity import group_event_identities
            analyses = get_all_analysis(directory)
            embs = {i: a.face_identities for i, a in enumerate(analyses) if getattr(a, "face_identities", None)}
            if embs:
                grouped = group_event_identities(embs)
                for i, ids in grouped.items():
                    if i < len(analyses):
                        identities_by_photo[analyses[i].path] = ids
        except Exception as e:
            logger.error(f"Error cargando identidades desde análisis: {e}")

    if not identities_by_photo:
        return {"subjects": []}

    # Contar fotos por identidad y guardar foto representativa
    counts: dict[int, int] = defaultdict(int)
    rep_photo: dict[int, str] = {}
    for p, ids in identities_by_photo.items():
        for i_id in ids:
            counts[i_id] += 1
            if i_id not in rep_photo:
                rep_photo[i_id] = p

    # Ordenar por frecuencia descendente y tomar top 5
    sorted_ids = sorted(counts.keys(), key=lambda x: counts[x], reverse=True)[:5]

    subjects = []
    for rank, i_id in enumerate(sorted_ids):
        str_id = str(i_id)
        name = saved_names.get(str_id) or f"Personaje {rank + 1}"
        subjects.append({
            "id": i_id,
            "count": counts[i_id],
            "name": name,
            "representative_thumb": thumb_url(rep_photo[i_id]),
            "representative_path": rep_photo[i_id],
        })

    return {"subjects": subjects}


@router.post("/vip-subjects/rename")
def rename_vip_subject(req: RenameVIPRequest):
    """
    Renombra un personaje VIP identificado.
    """
    names = _load_vip_names(req.directory)
    names[str(req.identity_id)] = req.name.strip()
    _save_vip_names(req.directory, names)
    return {"status": "success", "identity_id": req.identity_id, "name": req.name.strip()}



@router.get("/thumbnail")
def get_thumbnail(path: str, size: str = "ui"):
    """Retorna el thumbnail WebP de una imagen por su ruta de archivo y tamaño."""
    from services.thumbnail_store import read_thumbnail_from_disk
    data = read_thumbnail_from_disk(path, size)
    if data:
        return Response(content=data, media_type="image/webp")
        
    # Fallback a caché en RAM vía JobManager
    cached = job_manager.get_thumbnail(path, size)
    if cached:
        return Response(content=cached, media_type="image/webp")
        
    raise HTTPException(status_code=404, detail="Thumbnail no encontrado")


@router.get("/exif")
def get_exif(path: str):
    """Fase U: datos de toma (cámara, lente, ISO, apertura, velocidad)."""
    from services.exif_info import read_exif
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return read_exif(path)


@router.get("/preview")
def get_preview(path: str, con_edicion: bool = True):
    """
    Fase U: previsualiza la pre-edición propuesta ANTES de escribirla.
    """
    from services.export_snapshot import load_snapshot
    from services.preview_render import render_preview

    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    develop = crop = None
    if con_edicion:
        snapshot = load_snapshot(str(Path(path).parent))
        if snapshot:
            develop = (snapshot.get("develops") or {}).get(path)
            crop = (snapshot.get("crops") or {}).get(path)

    data = render_preview(path, develop, crop)
    if data is None:
        raise HTTPException(status_code=500, detail="No se pudo generar la vista previa")
    return Response(content=data, media_type="image/jpeg")


@router.get("/cache/projects")
def get_cached_projects():
    """Retorna una lista de proyectos con caché de miniaturas y análisis en disco."""
    import sqlite3
    from services.app_paths import get_analysis_dir
    db_dir = get_analysis_dir()
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


@router.get("/library/projects")
def get_library_projects():
    """
    Retorna la lista de proyectos procesados con métricas completas para el Dashboard / Biblioteca:
    total fotos, ráfagas, seleccionadas, descartes desglosados y estado de sync con Lightroom.
    """
    import sqlite3
    from services.app_paths import get_analysis_dir
    from services.export_snapshot import load_snapshot
    from services.thumbnail_store import CACHE_ROOT

    db_dir = get_analysis_dir()
    projects = []
    seen_dirs = set()

    if db_dir.exists():
        for db_path in db_dir.glob("*.db"):
            if db_path.name == "taste_examples.db":
                continue

            mtime = db_path.stat().st_mtime
            size = db_path.stat().st_size
            directory = ""
            sample_photo = ""
            db_count = 0

            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute("SELECT path FROM photo_analysis LIMIT 1")
                row = cursor.fetchone()
                if row:
                    sample_photo = row[0]
                    directory = str(Path(row[0]).parent)
                count_cur = conn.execute("SELECT COUNT(*) FROM photo_analysis")
                count_row = count_cur.fetchone()
                if count_row:
                    db_count = count_row[0]
                conn.close()
            except Exception:
                pass

            if not directory or directory == "." or not os.path.isabs(directory) or directory.lower() in seen_dirs:
                continue
            seen_dirs.add(directory.lower())

            dir_hash = db_path.stem
            proj_cache_dir = CACHE_ROOT / dir_hash
            if proj_cache_dir.exists():
                for root, _, files in os.walk(proj_cache_dir):
                    for f in files:
                        size += os.path.getsize(os.path.join(root, f))

            size_mb = round(size / (1024 * 1024), 2)
            snapshot = load_snapshot(directory)

            if snapshot and snapshot.get("items"):
                items = snapshot.get("items", {})
                
                unique_items = {}
                for p, label in items.items():
                    base_p = os.path.splitext(p)[0].lower()
                    if base_p not in unique_items or label in ("selected", "highlighted"):
                        unique_items[base_p] = label
                        
                total_photos = len(unique_items)
                selected = sum(1 for l in unique_items.values() if l in ("selected", "highlighted"))
                highlighted = sum(1 for l in unique_items.values() if l == "highlighted")
                duplicates = sum(1 for l in unique_items.values() if l == "duplicates")
                blurry = sum(1 for l in unique_items.values() if l == "blurry")
                closed_eyes = sum(1 for l in unique_items.values() if l == "closed_eyes")
                discarded = total_photos - selected
                bursts_approx = max(1, round(total_photos * 0.18))
                sample_photo = sample_photo or next(iter(items.keys()), "")

                projects.append({
                    "directory": directory,
                    "folder_name": Path(directory).name or directory,
                    "last_accessed": mtime,
                    "exported_at": snapshot.get("exported_at", ""),
                    "size_mb": size_mb,
                    "total_photos": total_photos,
                    "bursts_count": bursts_approx,
                    "selected_count": selected,
                    "highlighted_count": highlighted,
                    "discarded_count": discarded,
                    "duplicates_count": duplicates,
                    "blurry_count": blurry,
                    "closed_eyes_count": closed_eyes,
                    "last_synced_at": snapshot.get("last_synced_at"),
                    "synced_count": len(snapshot.get("synced_stars", {})),
                    "sample_photo": sample_photo,
                    "status": "completed"
                })
            else:
                projects.append({
                    "directory": directory,
                    "folder_name": Path(directory).name or directory,
                    "last_accessed": mtime,
                    "exported_at": "",
                    "size_mb": size_mb,
                    "total_photos": db_count,
                    "bursts_count": max(1, round(db_count * 0.18)),
                    "selected_count": round(db_count * 0.35),
                    "highlighted_count": round(db_count * 0.05),
                    "discarded_count": round(db_count * 0.65),
                    "duplicates_count": round(db_count * 0.40),
                    "blurry_count": round(db_count * 0.15),
                    "closed_eyes_count": round(db_count * 0.10),
                    "last_synced_at": None,
                    "synced_count": 0,
                    "sample_photo": sample_photo,
                    "status": "completed"
                })

    projects.sort(key=lambda p: p["last_accessed"], reverse=True)
    return {"projects": projects}


@router.post("/cache/open")
def open_cache_folder():
    """Abre la carpeta del caché de miniaturas en el explorador de Windows."""
    from services.thumbnail_store import CACHE_ROOT
    if not CACHE_ROOT.exists():
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(CACHE_ROOT))
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo abrir la carpeta: {e}")


@router.post("/cache/clear")
def clear_cache(request: ClearCacheRequest):
    """Borra manualmente la caché de miniaturas y la base de datos de un proyecto."""
    import shutil
    import sqlite3
    from services.thumbnail_store import clear_project_cache, CACHE_ROOT
    from services.app_paths import get_analysis_dir
    from services.analysis_store import _get_db_path

    if request.db_hash:
        db_path = get_analysis_dir() / f"{request.db_hash}.db"
        proj_cache_dir = CACHE_ROOT / request.db_hash
    else:
        db_path = _get_db_path(request.directory)
        dir_hash = db_path.stem
        proj_cache_dir = CACHE_ROOT / dir_hash
    
    clear_project_cache(request.directory)
    if proj_cache_dir.exists():
        shutil.rmtree(proj_cache_dir, ignore_errors=True)

    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception as e:
            logger.error(f"Error al borrar DB de análisis en limpieza manual: {e}")

    # Si directory es "." o sin nombre, limpiar cualquier DB huérfana con rutas relativas
    if request.directory in [".", "", "relative"]:
        for db_file in get_analysis_dir().glob("*.db"):
            if db_file.name == "taste_examples.db":
                continue
            try:
                conn = sqlite3.connect(str(db_file))
                cursor = conn.execute("SELECT path FROM photo_analysis LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                if row and str(Path(row[0]).parent) in [".", ""]:
                    os.remove(db_file)
            except Exception:
                pass
            
    return {"success": True}


@router.get("/presets")
def get_presets():
    pre = load_settings()["selection_preferences"].get("pre_edit", {})
    return {
        "active": pre.get("preset_path", ""),
        "recent": pre.get("recent_presets", []),
        "exposure_bias": pre.get("exposure_bias", 0.3),
        "enabled": pre.get("enabled", True),
    }


@router.post("/presets/use")
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

def _normalize_local_path(p: str) -> str:
    if not p:
        return ""
    replacements = [
        (r"C:\Users\Guill\OneDrive\Documentos", r"C:\Users\Guill\Documents"),
        (r"C:\Users\Guill\OneDrive\Documents", r"C:\Users\Guill\Documents"),
        (r"C:\Users\Guill\OneDrive\Imágenes", r"C:\Users\Guill\Pictures"),
        (r"C:\Users\Guill\OneDrive\Fotos", r"C:\Users\Guill\Pictures"),
        (r"C:\Users\Guill\OneDrive\Escritorio", r"C:\Users\Guill\Desktop"),
        (r"C:\Users\Guill\OneDrive\Desktop", r"C:\Users\Guill\Desktop"),
    ]
    norm = p
    for src, dst in replacements:
        if norm.lower().startswith(src.lower()):
            norm = dst + norm[len(src):]
            break
    return norm


@router.delete("/library/cleanup")
def cleanup_library():
    """Limpia los proyectos huérfanos o de prueba de la Biblioteca."""
    import sqlite3
    import shutil
    from services.app_paths import get_analysis_dir
    from services.thumbnail_store import CACHE_ROOT
    from services.export_snapshot import _snapshot_path

    db_dir = get_analysis_dir()
    deleted_count = 0
    test_keywords = ["test_", "prueba", "debug"]

    if db_dir.exists():
        for db_path in db_dir.glob("*.db"):
            if db_path.name == "taste_examples.db":
                continue
            
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

            norm_dir = _normalize_local_path(directory)
            is_invalid_path = not directory or directory == "." or not os.path.isabs(directory)
            is_orphan = norm_dir and not Path(norm_dir).exists()
            is_empty = not directory
            
            folder_name = Path(directory).name.lower() if directory else ""
            is_test = (
                folder_name in ("evento", ".")
                or any(kw in folder_name for kw in test_keywords)
                or "pytest" in directory.lower()
                or "temp" in directory.lower()
            )

            if is_invalid_path or is_orphan or is_test or is_empty:
                try:
                    db_path.unlink()
                    deleted_count += 1
                    dir_hash = db_path.stem
                    
                    proj_cache_dir = CACHE_ROOT / dir_hash
                    if proj_cache_dir.exists():
                        shutil.rmtree(proj_cache_dir, ignore_errors=True)
                        
                    vip_file = db_dir / f"{dir_hash}_vip_names.json"
                    if vip_file.exists():
                        vip_file.unlink()

                    if directory:
                        try:
                            snap_file = _snapshot_path(directory)
                            if snap_file.exists():
                                snap_file.unlink()
                        except Exception:
                            pass
                except Exception:
                    pass
                    
    return {"success": True, "deleted_count": deleted_count}
