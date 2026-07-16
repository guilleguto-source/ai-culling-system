import pytest
from fastapi.testclient import TestClient
from main import app
from pathlib import Path
from services.analysis import PhotoAnalysis
from services.analysis_store import init_store, save_analysis
import os

client = TestClient(app)

def test_debug_overlay_404_not_found():
    # Caso archivo no existe
    response = client.get("/debug/overlay?path=nonexistent.jpg")
    assert response.status_code == 404

def test_debug_overlay_no_analysis(tmp_path):
    # Crear un JPG temporal de prueba
    from PIL import Image
    import numpy as np
    
    img_path = tmp_path / "test_img.jpg"
    img = Image.fromarray(np.zeros((100, 100, 3), dtype=np.uint8))
    img.save(str(img_path))
    
    # Hacer GET sin análisis guardado
    response = client.get(f"/debug/overlay?path={img_path}")
    assert response.status_code == 404
    assert "El análisis no está en base de datos" in response.json()["detail"]

def test_debug_overlay_success(tmp_path):
    # Crear un JPG temporal de prueba
    from PIL import Image
    import numpy as np
    
    img_path = tmp_path / "test_img.jpg"
    img = Image.fromarray(np.zeros((100, 100, 3), dtype=np.uint8))
    img.save(str(img_path))
    
    # Crear y guardar análisis en SQLite
    conn = init_store(str(tmp_path))
    analysis = PhotoAnalysis(
        index=0,
        path=str(img_path),
        scene_type="portrait",
        face_bboxes=[[10, 10, 30, 30]],
        face_sharpness=[100.0],
        any_closed_eyes=False,
        blur_score=150.0,
        blur_flag=False,
        sharp_anywhere=150.0,
        aesthetic_score=0.9
    )
    mtime = os.path.getmtime(str(img_path))
    save_analysis(conn, analysis, mtime)
    
    # Hacer GET del overlay
    response = client.get(f"/debug/overlay?path={img_path}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    # Debe ser una imagen WebP válida (verificar firma de archivo bytes)
    # Los archivos WebP empiezan con RIFF...WEBP
    content = response.content
    assert content.startswith(b"RIFF")
    assert b"WEBP" in content[:16]
