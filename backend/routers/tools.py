from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from pathlib import Path
from typing import Optional, List
from PIL import Image
import io

from core.job_manager import job_manager
from services.thumbnail_store import get_thumbnail_cache_paths
from services.xmp_exporter import write_xmp
from services.export_snapshot import load_snapshot

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
