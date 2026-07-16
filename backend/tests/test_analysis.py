import pytest
import numpy as np
from services.analysis import analyze_photo, PhotoAnalysis
from services.ingester import ImageRecord
from pathlib import Path

def test_analyze_photo_no_thumb():
    record = ImageRecord(
        path="test.jpg",
        filename="test.jpg",
        is_raw=False,
        thumb_ai=None,
        error="Fallo al cargar"
    )
    # Debería devolver un PhotoAnalysis con error sin fallar
    analysis = analyze_photo(
        index=0,
        record=record,
        face_detector=None,
        eye_session=None,
        blur_threshold=100.0,
        detect_closed_eyes=True,
        pre_edit_enabled=False
    )
    
    assert analysis.error == "Error previo o falta thumb_ai"
    assert analysis.index == 0
    assert analysis.path == "test.jpg"

def test_analyze_photo_valid_no_face_detector():
    # Simulamos una imagen válida pequeña negra
    thumb = np.zeros((100, 100, 3), dtype=np.uint8)
    record = ImageRecord(
        path="test_valid.jpg",
        filename="test_valid.jpg",
        is_raw=False,
        thumb_ai=thumb
    )
    
    analysis = analyze_photo(
        index=1,
        record=record,
        face_detector=None,  # Sin detector de caras
        eye_session=None,
        blur_threshold=100.0,
        detect_closed_eyes=True,
        pre_edit_enabled=False
    )
    
    assert not analysis.error
    assert analysis.scene_type == "detail"
    assert analysis.face_bboxes == []
    # Al ser un array negro, la nitidez laplaciana debería ser 0
    assert analysis.blur_score == 0.0
    assert analysis.blur_flag is True  # 0.0 < 100.0 (blur_threshold)
    assert analysis.sharp_anywhere == 0.0
