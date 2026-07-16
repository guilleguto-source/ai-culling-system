import pytest
import numpy as np
from services.ingester import get_ingest_tasks, process_single_image
from main import _run_culling_pipeline, _job_state
from pathlib import Path

def test_get_ingest_tasks(tmp_path):
    # Crear un par de imágenes sintéticas
    (tmp_path / "img1.jpg").write_text("dummy")
    (tmp_path / "img1.cr2").write_text("dummy") # RAW emparejado
    (tmp_path / "img2.jpg").write_text("dummy")
    
    tasks = get_ingest_tasks(str(tmp_path))
    
    assert len(tasks) == 2
    # El de img1.jpg debe estar emparejado con img1.cr2
    img1_task = [t for t in tasks if t[0].name == "img1.jpg"]
    assert len(img1_task) == 1
    assert img1_task[0][1] is not None
    assert "img1.cr2" in img1_task[0][1]
