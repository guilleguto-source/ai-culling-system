from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import io

from core.job_manager import job_manager
from services.thumbnail_store import get_thumbnail_cache_paths
from services.xmp_exporter import write_xmp, update_file_metadata
from services.export_snapshot import load_snapshot
from services.metadata_manager import (
    get_metadata_profiles,
    save_or_update_profile,
    delete_metadata_profile,
    set_default_profile,
    detect_gps_in_directory,
    build_batch_metadata_payload,
    EVENT_TAXONOMY,
    ECUADOR_CITIES,
)

router = APIRouter()

class ExportPreviewsRequest(BaseModel):
    input_dir: str
    output_dir: str
    filter_mode: str = "all"

@router.post("/export-previews")
def export_previews(req: ExportPreviewsRequest):
    output_path = Path(req.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    paths_to_process = []
    snapshot = load_snapshot(req.input_dir)
    
    if snapshot and snapshot.get("items"):
        for path_str, label in snapshot["items"].items():
            if req.filter_mode == 'selected' and label not in ('selected', 'highlighted'):
                continue
            paths_to_process.append(path_str)
    else:
        input_path = Path(req.input_dir)
        if not input_path.exists() or not input_path.is_dir():
            raise HTTPException(status_code=400, detail="El directorio origen no existe")
            
        valid_extensions = {".jpg", ".jpeg", ".cr2", ".cr3", ".arw", ".dng", ".raf", ".nef"}
        all_paths = [str(f) for f in input_path.rglob("*") if f.is_file() and f.suffix.lower() in valid_extensions]
        
        if req.filter_mode == 'selected':
            results = job_manager.get_results()
            if not results:
                raise HTTPException(status_code=400, detail="No hay resultados en memoria para filtrar por seleccionadas. Usa 'Exportar Todas'.")
            valid_paths = {r.path for r in results if r.label in ('selected', 'highlighted')}
            paths_to_process = [p for p in all_paths if p in valid_paths]
        else:
            paths_to_process = all_paths

    exported_count = 0
    errors = 0
    
    for file_str in paths_to_process:
        _, duel_path = get_thumbnail_cache_paths(file_str)
        if duel_path.exists():
            try:
                webp_data = duel_path.read_bytes()
                img = Image.open(io.BytesIO(webp_data))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                stem = Path(file_str).stem
                out_file = output_path / f"{stem}.jpg"
                img.save(out_file, "JPEG", quality=90)
                exported_count += 1
            except Exception as e:
                errors += 1
                print(f"Error exporting {Path(file_str).name}: {e}")
                
    return {"status": "ok", "exported": exported_count, "errors": errors}

class ImportSelectionRequest(BaseModel):
    base_dir: str
    client_folder: Optional[str] = None
    filenames: Optional[List[str]] = None

@router.post("/import-selection")
def import_selection(req: ImportSelectionRequest):
    target_stems = set()
    
    if req.client_folder:
        client_path = Path(req.client_folder)
        if client_path.exists() and client_path.is_dir():
            for f in client_path.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    target_stems.add(f.stem.lower())
                    
    if req.filenames:
        for name in req.filenames:
            if name.strip():
                stem = Path(name.strip()).stem.lower()
                if stem:
                    target_stems.add(stem)
                
    if not target_stems:
        raise HTTPException(status_code=400, detail="No se proporcionaron archivos o la carpeta está vacía")
        
    paths_to_check = []
    snapshot = load_snapshot(req.base_dir)
    
    if snapshot and snapshot.get("items"):
        paths_to_check = list(snapshot["items"].keys())
    else:
        base_path = Path(req.base_dir)
        if not base_path.exists() or not base_path.is_dir():
            raise HTTPException(status_code=400, detail="El directorio base no existe")
        valid_extensions = {".jpg", ".jpeg", ".cr2", ".cr3", ".arw", ".dng", ".raf", ".nef"}
        paths_to_check = [str(f) for f in base_path.rglob("*") if f.is_file() and f.suffix.lower() in valid_extensions]

    updated_count = 0
    
    for file_str in paths_to_check:
        f = Path(file_str)
        if f.stem.lower() in target_stems:
            try:
                write_xmp(
                    image_path=file_str,
                    label="Red",
                    stars=4,
                    color="Red",
                    flag="pick",
                    overwrite=True
                )
                updated_count += 1
            except Exception as e:
                print(f"Error updating XMP for {f.name}: {e}")
                
    return {"status": "ok", "updated": updated_count}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints de Gestión de Metadatos & Copyright
# ─────────────────────────────────────────────────────────────────────────────

class ProfileRequest(BaseModel):
    id: Optional[str] = None
    name: str
    creator: str = ""
    copyright_notice: str = ""
    credit: str = ""
    usage_terms: str = ""
    web_statement: str = ""
    is_default: bool = False


class DetectGPSRequest(BaseModel):
    directory: str


class ApplyMetadataRequest(BaseModel):
    directory: str
    filter_mode: str = "all"  # "all" | "selected"
    profile_id: Optional[str] = None
    profile_custom: Optional[dict] = None
    event_type: str = "general"
    age: Optional[str] = None
    protagonist: Optional[str] = None
    city: Optional[str] = None
    custom_tags: Optional[str] = None
    keywords_mode: str = "append"  # "append" | "replace"


@router.get("/metadata/config")
def get_metadata_config():
    """Retorna los perfiles guardados, la lista de ciudades de Ecuador y la taxonomía de eventos."""
    profiles = get_metadata_profiles()
    return {
        "profiles": profiles,
        "taxonomy": EVENT_TAXONOMY,
        "cities": list(ECUADOR_CITIES.keys())
    }


@router.post("/metadata/profiles")
def save_profile_endpoint(req: ProfileRequest):
    data = req.dict()
    saved = save_or_update_profile(data)
    return {"status": "ok", "profile": saved}


@router.delete("/metadata/profiles/{profile_id}")
def delete_profile_endpoint(profile_id: str):
    ok = delete_metadata_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {"status": "ok"}


@router.post("/metadata/profiles/{profile_id}/set-default")
def set_default_profile_endpoint(profile_id: str):
    ok = set_default_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return {"status": "ok"}


@router.post("/metadata/detect-gps")
def detect_gps_endpoint(req: DetectGPSRequest):
    res = detect_gps_in_directory(req.directory)
    return res


@router.post("/metadata/apply-batch")
def apply_batch_metadata_endpoint(req: ApplyMetadataRequest):
    base_path = Path(req.directory)
    if not base_path.exists() or not base_path.is_dir():
        raise HTTPException(status_code=400, detail="El directorio origen no existe")

    # 1. Determinar el perfil a aplicar
    profile = req.profile_custom
    if not profile:
        profiles = get_metadata_profiles()
        if req.profile_id:
            profile = next((p for p in profiles if p.get("id") == req.profile_id), None)
        if not profile:
            profile = next((p for p in profiles if p.get("is_default")), None)
        if not profile and profiles:
            profile = profiles[0]
        if not profile:
            profile = {
                "name": "Por defecto",
                "creator": "",
                "copyright_notice": "© {year} Todos los derechos reservados."
            }

    # 2. Armar el payload de metadatos estandarizados
    payload = build_batch_metadata_payload(
        profile=profile,
        event_type=req.event_type,
        age=req.age,
        protagonist=req.protagonist,
        city=req.city,
        custom_tags_str=req.custom_tags
    )

    # 3. Filtrar los archivos a modificar
    valid_extensions = {".jpg", ".jpeg", ".cr2", ".cr3", ".arw", ".dng", ".raf", ".nef"}
    all_files = [str(f) for f in base_path.rglob("*") if f.is_file() and f.suffix.lower() in valid_extensions]

    paths_to_process = []
    if req.filter_mode == "selected":
        snapshot = load_snapshot(req.directory)
        if snapshot and snapshot.get("items"):
            valid_selected = {
                p for p, label in snapshot["items"].items()
                if label in ("selected", "highlighted", "Red", "Green", "Yellow", "Blue")
            }
            paths_to_process = [p for p in all_files if p in valid_selected]
        else:
            results = job_manager.get_results()
            if results:
                valid_selected = {
                    r.path for r in results
                    if r.label in ("selected", "highlighted") or (getattr(r, "stars", 0) >= 4)
                }
                paths_to_process = [p for p in all_files if p in valid_selected]
            else:
                paths_to_process = all_files
    else:
        paths_to_process = all_files

    if not paths_to_process:
        raise HTTPException(status_code=400, detail="No se encontraron fotografías para procesar con los filtros indicados")

    unique_paths = []
    seen_stems = set()
    for file_path in paths_to_process:
        p = Path(file_path)
        stem_key = (str(p.parent).lower(), p.stem.lower())
        if stem_key in seen_stems:
            continue
        seen_stems.add(stem_key)
        unique_paths.append(file_path)

    def _process_file(fpath: str) -> bool:
        try:
            return update_file_metadata(
                image_path=fpath,
                metadata=payload,
                keywords_mode=req.keywords_mode,
                update_dual_partner=True
            )
        except Exception:
            return False

    updated_count = 0
    errors_count = 0
    max_workers = min(16, max(4, (os.cpu_count() or 4) * 2))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_file, fpath): fpath for fpath in unique_paths}
        for future in as_completed(futures):
            try:
                ok = future.result()
                if ok:
                    updated_count += 1
                else:
                    errors_count += 1
            except Exception:
                errors_count += 1

    return {
        "status": "ok",
        "updated_shots": updated_count,
        "errors": errors_count,
        "applied_metadata": payload
    }

