"""
test_face_engine_contract.py — Verifica el contrato del Patrón Adaptador de detección facial.
"""
import pytest
import numpy as np
from services.face_engine_adapter import DetectedFace, FaceEngineAdapter

def test_detected_face_dataclass():
    face = DetectedFace(
        bbox=[10, 20, 100, 120],
        confidence=0.95,
        landmarks=[[15, 25], [45, 25], [30, 50], [20, 80], [40, 80]],
        embedding=np.zeros(512, dtype=np.float32)
    )
    assert face.bbox == [10, 20, 100, 120]
    assert face.confidence == 0.95
    assert len(face.landmarks) == 5
    assert face.embedding.shape == (512,)

def test_face_engine_adapter_mock_analyze(monkeypatch):
    class MockUniFaceResult:
        bbox_xywh = [100, 150, 80, 90]
        confidence = 0.88
        landmarks = np.array([[110, 160], [170, 160], [140, 180], [120, 210], [160, 210]])
        embedding = np.ones(512, dtype=np.float32)

    class MockAnalyzer:
        def __init__(self, *args, **kwargs):
            pass
        def analyze(self, img):
            return [MockUniFaceResult()]

    import uniface
    monkeypatch.setattr(uniface, "FaceAnalyzer", MockAnalyzer)

    adapter = FaceEngineAdapter()
    dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
    faces = adapter.analyze(dummy_img)

    assert len(faces) == 1
    assert faces[0].bbox == [100, 150, 80, 90]
    assert faces[0].confidence == 0.88
    assert len(faces[0].landmarks) == 5
    assert faces[0].embedding.shape == (512,)

    adapter.release()
    assert adapter._analyzer is None
