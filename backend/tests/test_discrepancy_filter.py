"""
test_discrepancy_filter.py — Pruebas del filtro de discrepancias y Safety Cap.
"""
from types import SimpleNamespace
from services.discrepancy_filter import find_discrepancies, _check_no_faces, _check_crowd, _check_tiny_faces

def _mock_analysis(face_count=1, face_bboxes=None, error=None):
    return SimpleNamespace(
        face_count=face_count,
        face_bboxes=face_bboxes or [[10, 10, 80, 80]],
        face_attrs=[{"confidence": 0.90}] if face_count > 0 else [],
        error=error
    )

def test_find_discrepancies_no_faces():
    analyses = [
        _mock_analysis(face_count=0, face_bboxes=[]),  # duda
        _mock_analysis(face_count=2, face_bboxes=[[10, 10, 80, 80], [100, 100, 80, 80]]),
    ]
    dudas = find_discrepancies(analyses, max_discrepancy_ratio=0.50)
    assert dudas == [0]

def test_find_discrepancies_crowd():
    analyses = [
        _mock_analysis(face_count=10, face_bboxes=[[10, 10, 50, 50]] * 10), # duda (crowd)
        _mock_analysis(face_count=2),
    ]
    dudas = find_discrepancies(analyses, max_discrepancy_ratio=0.50)
    assert dudas == [0]

def test_find_discrepancies_tiny_faces():
    analyses = [
        _mock_analysis(face_count=1, face_bboxes=[[10, 10, 20, 20]]), # duda (tiny < 40px)
        _mock_analysis(face_count=1, face_bboxes=[[10, 10, 80, 80]]), # ok
    ]
    dudas = find_discrepancies(analyses, max_discrepancy_ratio=0.50)
    assert dudas == [0]

def test_find_discrepancies_safety_cap():
    # 10 fotos, todas dudosas (0 caras), pero con safety cap de 30%
    analyses = [_mock_analysis(face_count=0, face_bboxes=[]) for _ in range(10)]
    dudas = find_discrepancies(analyses, max_discrepancy_ratio=0.30)
    assert len(dudas) == 3
