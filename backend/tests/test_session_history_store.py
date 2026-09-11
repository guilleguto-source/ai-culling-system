"""
test_session_history_store.py — Tests del almacén de retención histórica y estimador dinámico.
"""
from pathlib import Path
from services.session_history_store import SessionHistoryStore

def test_session_history_store_empty(tmp_path):
    store = SessionHistoryStore(db_path=tmp_path / "test_session.db")
    est = store.get_estimate(total_photos=1000, event_type="wedding", selectivity="standard")
    
    assert est["total_photos"] == 1000
    assert not est["is_calibrated"]
    assert est["samples_count"] == 0
    assert est["estimated_percentage"] == 35
    assert 300 <= est["min_photos"] <= 400

def test_session_history_store_learning(tmp_path):
    store = SessionHistoryStore(db_path=tmp_path / "test_session.db")
    
    # Registrar 3 sesiones donde el fotógrafo retiene ~22%
    store.record_session("/path/1", "kids_party", "standard", 1000, 350, 220)
    store.record_session("/path/2", "kids_party", "standard", 1000, 350, 210)
    store.record_session("/path/3", "kids_party", "standard", 1000, 350, 230)
    
    est = store.get_estimate(total_photos=1000, event_type="kids_party", selectivity="standard")
    
    assert est["is_calibrated"]
    assert est["samples_count"] == 3
    # Debe haber bajado significativamente del 35% teórico hacia el ~22% real
    assert est["estimated_percentage"] < 30
