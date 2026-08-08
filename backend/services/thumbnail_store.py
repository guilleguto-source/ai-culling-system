import hashlib
from pathlib import Path
from urllib.parse import quote
import os
import shutil
import time


def thumb_url(file_path: str, size: str = "ui") -> str:
    """URL relativa del endpoint /thumbnail para una foto. Única fuente del
    formato: ruta URL-encodeada (las carpetas reales tienen espacios y tildes)
    y el parámetro se llama `size` — un 'type=' escrito a mano ya rompió dos
    features en silencio."""
    return f"/thumbnail?path={quote(file_path)}&size={size}"

from services.app_paths import get_user_data_dir as _get_user_data_dir

# Anclado a get_user_data_dir() para compatibilidad empaquetada y dev
CACHE_ROOT = _get_user_data_dir() / "cache" / "thumbnails"

def _get_hashes(file_path: str) -> tuple[str, str]:
    p = Path(file_path)
    parent_str = str(p.parent).lower()
    file_str = str(p).lower()
    
    dir_hash = hashlib.md5(parent_str.encode('utf-8')).hexdigest()
    file_hash = hashlib.md5(file_str.encode('utf-8')).hexdigest()
    return dir_hash, file_hash

def get_thumbnail_cache_paths(file_path: str) -> tuple[Path, Path]:
    dir_hash, file_hash = _get_hashes(file_path)
    proj_dir = CACHE_ROOT / dir_hash
    ui_path = proj_dir / "ui" / f"{file_hash}.webp"
    duel_path = proj_dir / "duel" / f"{file_hash}.webp"
    return ui_path, duel_path

def save_thumbnail_to_disk(file_path: str, thumb_ui: bytes, thumb_duel: bytes):
    ui_path, duel_path = get_thumbnail_cache_paths(file_path)
    
    ui_path.parent.mkdir(parents=True, exist_ok=True)
    duel_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(ui_path, "wb") as f:
        f.write(thumb_ui)
    with open(duel_path, "wb") as f:
        f.write(thumb_duel)

def read_thumbnail_from_disk(file_path: str, size: str = "ui") -> bytes | None:
    ui_path, duel_path = get_thumbnail_cache_paths(file_path)
    target = duel_path if size == "duel" else ui_path
    
    if target.exists():
        # Actualizar mtime del directorio del proyecto para la limpieza de 30 días
        try:
            target.parent.parent.touch(exist_ok=True)
        except Exception:
            pass
        return target.read_bytes()
    return None

def clear_project_cache(directory: str):
    parent_str = str(Path(directory).resolve()).lower()
    dir_hash = hashlib.md5(parent_str.encode('utf-8')).hexdigest()
    proj_dir = CACHE_ROOT / dir_hash
    if proj_dir.exists():
        shutil.rmtree(proj_dir)

def auto_cleanup_cache(days: int = 30):
    if not CACHE_ROOT.exists():
        return
    now = time.time()
    cutoff = now - (days * 24 * 3600)
    for proj_dir in CACHE_ROOT.iterdir():
        if proj_dir.is_dir():
            # Si el directorio no ha sido modificado (leído/tocado) en 30 días, borrarlo
            mtime = proj_dir.stat().st_mtime
            if mtime < cutoff:
                try:
                    shutil.rmtree(proj_dir)
                except Exception:
                    pass
