import pytest
import sqlite3
import os
from services.analysis import PhotoAnalysis
from services.analysis_store import init_store, load_analysis, save_analysis, _get_db_path

def test_analysis_store_roundtrip(tmp_path):
    conn = init_store(str(tmp_path))
    
    analysis = PhotoAnalysis(
        index=0,
        path="test.jpg",
        scene_type="portrait",
        face_bboxes=[[10, 20, 30, 40]],
        eye_landmarks=[[15, 25]],
        face_sharpness=[0.95],
        any_closed_eyes=True,
        blur_score=50.5,
        blur_flag=False,
        sharp_anywhere=60.0,
        aesthetic_score=0.8,
        saliency_region=[0, 0, 100, 100],
        pre_skin_lum=0.4,
        pre_global_lum=0.5,
        pre_clip_frac=0.01,
        pre_wb=(1.2, 0.9),
        error=""
    )
    
    mtime = 12345.0
    
    # Save it
    save_analysis(conn, analysis, mtime)
    
    # Load it
    loaded = load_analysis(conn, "test.jpg", mtime)
    
    assert loaded is not None
    assert loaded.scene_type == "portrait"
    assert loaded.face_bboxes == [[10, 20, 30, 40]]
    assert loaded.blur_score == 50.5
    assert loaded.pre_wb == (1.2, 0.9)
    assert loaded.any_closed_eyes is True
    
    # Load with wrong mtime
    loaded_wrong = load_analysis(conn, "test.jpg", 99999.0)
    assert loaded_wrong is None


def test_atributos_de_mediapipe_persisten(tmp_path):
    """Regresión: los conteos de caras deciden los descartes; si no se
    persisten, al leer del caché toda foto parece sin problemas."""
    conn = init_store(str(tmp_path))
    a = PhotoAnalysis(
        index=3, path="grupal.jpg", scene_type="portrait",
        face_bboxes=[[0, 0, 10, 10]] * 43,   # YuNet ve 43 (incluye decoración)
        face_count=43, valid_face_count=7,   # MediaPipe valida 7
        closed_eyes_count=2, looking_away_count=3, smiling_count=4,
        any_closed_eyes=True,
    )
    save_analysis(conn, a, 111.0)
    l = load_analysis(conn, "grupal.jpg", 111.0)

    assert l.face_count == 43
    assert l.valid_face_count == 7
    assert l.closed_eyes_count == 2
    assert l.looking_away_count == 3
    assert l.smiling_count == 4


def test_refresh_mtimes_tras_escribir_xmp(tmp_path):
    """Regresión: el pipeline escribe el XMP DENTRO del JPG al terminar, lo que
    cambia el mtime e invalidaba el análisis recién guardado — el caché nunca
    acertaba y la re-selección 'instantánea' re-analizaba todo."""
    import os
    from services.analysis_store import refresh_mtimes

    foto = tmp_path / "a.jpg"
    foto.write_bytes(b"pixeles originales")
    conn = init_store(str(tmp_path))
    save_analysis(conn, PhotoAnalysis(index=0, path=str(foto)), os.path.getmtime(foto))
    assert load_analysis(conn, str(foto), os.path.getmtime(foto)) is not None

    # simula el export XMP: reescribe el archivo (mtime nuevo)
    os.utime(foto, (0, 99999))
    assert load_analysis(conn, str(foto), os.path.getmtime(foto)) is None, \
        "el análisis debe invalidarse si el archivo cambia"

    # re-sellar lo revalida sin re-analizar
    assert refresh_mtimes(conn, [str(foto)]) == 1
    assert load_analysis(conn, str(foto), os.path.getmtime(foto)) is not None


def test_refresh_mtimes_ignora_faltantes(tmp_path):
    conn = init_store(str(tmp_path))
    from services.analysis_store import refresh_mtimes
    assert refresh_mtimes(conn, [str(tmp_path / "no-existe.jpg")]) == 0


def test_version_vieja_invalida_el_cache(tmp_path):
    """Un análisis guardado con un esquema anterior no debe reusarse."""
    from services import analysis_store
    conn = init_store(str(tmp_path))
    save_analysis(conn, PhotoAnalysis(index=0, path="x.jpg"), 5.0)
    assert load_analysis(conn, "x.jpg", 5.0) is not None

    original = analysis_store.ANALYSIS_VERSION
    try:
        analysis_store.ANALYSIS_VERSION = original + 1
        assert load_analysis(conn, "x.jpg", 5.0) is None
    finally:
        analysis_store.ANALYSIS_VERSION = original
