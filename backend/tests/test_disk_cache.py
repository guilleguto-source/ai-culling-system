import pytest
from services.thumbnail_store import save_thumbnail_to_disk, read_thumbnail_from_disk, get_thumbnail_cache_paths, clear_project_cache, auto_cleanup_cache, CACHE_ROOT
import shutil
import time

def test_thumbnail_disk_cache_roundtrip(tmp_path):
    # Crear paths ficticios
    img_path = str(tmp_path / "event" / "photo1.jpg")
    
    thumb_ui = b"ui_webp_bytes"
    thumb_duel = b"duel_webp_bytes"
    
    # Guardar
    save_thumbnail_to_disk(img_path, thumb_ui, thumb_duel)
    
    # Verificar paths creados
    ui_path, duel_path = get_thumbnail_cache_paths(img_path)
    assert ui_path.exists()
    assert duel_path.exists()
    
    # Leer
    loaded_ui = read_thumbnail_from_disk(img_path, "ui")
    loaded_duel = read_thumbnail_from_disk(img_path, "duel")
    
    assert loaded_ui == thumb_ui
    assert loaded_duel == thumb_duel

def test_clear_project_cache(tmp_path):
    img_path = str(tmp_path / "project_a" / "photo.jpg")
    save_thumbnail_to_disk(img_path, b"1", b"2")
    
    ui_path, _ = get_thumbnail_cache_paths(img_path)
    assert ui_path.exists()
    
    # Limpiar caché del proyecto
    clear_project_cache(str(tmp_path / "project_a"))
    
    assert not ui_path.exists()
    
def test_auto_cleanup_cache(tmp_path):
    img_path = str(tmp_path / "project_b" / "photo.jpg")
    save_thumbnail_to_disk(img_path, b"1", b"2")
    
    ui_path, duel_path = get_thumbnail_cache_paths(img_path)
    
    # Modificar mtime del directorio del proyecto ficticio a hace 40 días
    proj_dir = ui_path.parent.parent
    forty_days_ago = time.time() - (40 * 24 * 3600)
    os_utime = os_utime = getattr(time, "utime", None)
    import os
    os.utime(str(proj_dir), (forty_days_ago, forty_days_ago))
    
    # Correr auto-cleanup (retención 30 días)
    auto_cleanup_cache(days=30)
    
    assert not proj_dir.exists()
