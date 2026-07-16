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
