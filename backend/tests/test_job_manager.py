"""
Pruebas unitarias y de concurrencia para el JobManager thread-safe.
"""
import threading
import time
from core.job_manager import JobManager


def test_job_manager_lifecycle():
    jm = JobManager()
    assert jm.get_status()["status"] == "idle"
    assert not jm.is_running

    assert jm.start_job("job_123", mode="cull") is True
    assert jm.is_running
    assert jm.get_status()["job_id"] == "job_123"
    assert jm.get_status()["status"] == "running"

    # No debe permitir iniciar un segundo job simultáneo
    assert jm.start_job("job_456") is False

    jm.update_progress(processed=10, total=50, progress=20.0, phase_text="Analizando")
    status = jm.get_status()
    assert status["processed"] == 10
    assert status["total"] == 50
    assert status["progress"] == 20.0
    assert status["phase_text"] == "Analizando"

    # Dict-like access
    assert jm["status"] == "running"
    assert jm.get("processed") == 10

    jm.set_results([{"path": "photo1.jpg", "label": "selected"}], {"total_images": 50})
    assert not jm.is_running
    assert jm.get_status()["status"] == "completed"
    assert jm.get_status()["progress"] == 100.0

    status_str, results, stats = jm.get_results()
    assert status_str == "completed"
    assert len(results) == 1
    assert stats["total_images"] == 50


def test_job_manager_error():
    jm = JobManager()
    jm.start_job("job_err")
    jm.set_error("Disco lleno")
    status = jm.get_status()
    assert status["status"] == "error"
    assert status["error"] == "Disco lleno"


def test_job_manager_thumbnail_cache():
    jm = JobManager()
    jm.set_thumbnail("p1.jpg", b"thumb_data_ui", size="ui")
    jm.set_thumbnail("p1.jpg", b"thumb_data_duel", size="duel")

    assert jm.get_thumbnail("p1.jpg", size="ui") == b"thumb_data_ui"
    assert jm.get_thumbnail("p1.jpg", size="duel") == b"thumb_data_duel"
    assert jm.get_thumbnail("nonexistent.jpg") is None

    jm.clear_thumbnails()
    assert jm.get_thumbnail("p1.jpg") is None


def test_job_manager_concurrency_stress():
    """Simula 20 hilos accediendo, escribiendo progreso y leyendo miniaturas simultáneamente."""
    jm = JobManager()
    jm.start_job("job_concurrent")

    errors = []

    def worker_progress(worker_id):
        try:
            for i in range(100):
                jm.update_progress(processed=i, total=100, progress=float(i), phase_text=f"Worker {worker_id}")
                jm.set_stat(f"stat_{worker_id}", i)
                _ = jm.get_status()
                _ = jm["status"]
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    def worker_thumbs(worker_id):
        try:
            for i in range(100):
                path = f"img_{worker_id}_{i}.jpg"
                jm.set_thumbnail(path, f"data_{i}".encode("utf-8"))
                val = jm.get_thumbnail(path)
                assert val == f"data_{i}".encode("utf-8")
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    threads = []
    for wid in range(10):
        t1 = threading.Thread(target=worker_progress, args=(wid,))
        t2 = threading.Thread(target=worker_thumbs, args=(wid,))
        threads.extend([t1, t2])

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0, f"Ocurrieron errores de concurrencia: {errors}"


def test_job_manager_phases_and_reset():
    jm = JobManager()
    expected_ids = ["thumbnails", "analysis", "clustering", "selection", "pre_edit", "export"]
    
    # Check initial phases
    phase_ids = [p["id"] for p in jm.get_status()["phases"]]
    assert phase_ids == expected_ids

    # Start job
    jm.start_job("job_phases_test")
    status = jm.get_status()
    assert [p["id"] for p in status["phases"]] == expected_ids

    # Update phase progress
    jm.update_phase_progress("selection", 25, 100)
    status = jm.get_status()
    selection_phase = next(p for p in status["phases"] if p["id"] == "selection")
    assert selection_phase["status"] == "running"
    assert selection_phase["progress"] == 25
    assert status["processed"] == 25
    assert status["total"] == 100

    # Complete phase
    jm.complete_phase("selection")
    status = jm.get_status()
    selection_phase = next(p for p in status["phases"] if p["id"] == "selection")
    assert selection_phase["status"] == "completed"
    assert selection_phase["progress"] == 100

    # Reset
    jm.reset()
    status = jm.get_status()
    assert status["status"] == "idle"
    assert [p["id"] for p in status["phases"]] == expected_ids

