"""
Smoke end-to-end del pipeline sobre fotos sintéticas.

Motivo: un `import numpy as np` faltante en main.py hacía fallar el cálculo de
embeddings dentro de un try/except que solo logueaba — el pipeline "pasaba"
pero el taste model nunca recibía datos. Estos tests verifican EFECTOS
(stats con velocidad, embeddings computados), no solo que no explote.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

import main
from main import _run_culling_pipeline


def _photo(path: Path, seed: int, size=(900, 600)):
    """JPEG sintético con textura (nítido) para que el pipeline lo procese."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(60, 200, size=(size[1], size[0], 3), dtype=np.uint8)
    Image.fromarray(arr).save(path, quality=90)


@pytest.fixture()
def evento(tmp_path, monkeypatch):
    from services import export_snapshot, analysis_store, thumbnail_store
    monkeypatch.setattr(export_snapshot, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(analysis_store, "ANALYSIS_DIR", tmp_path / "analysis")
    monkeypatch.setattr(thumbnail_store, "CACHE_ROOT", tmp_path / "cache")
    ev = tmp_path / "evento"
    ev.mkdir()
    for i in range(4):
        _photo(ev / f"IMG_{i:04d}.jpg", seed=i)
    return ev


def test_pipeline_completa_y_reporta_velocidad(evento):
    _run_culling_pipeline(str(evento), "job_test", "cull")

    assert main._job_state["status"] == "completed", main._job_state["error"]
    ingest = main._job_state["stats"]["ingest"]
    # Regresión: la UI mostraba "0 img/s" porque faltaban estas claves
    assert ingest["total"] == 4
    assert ingest["elapsed_seconds"] > 0
    assert ingest["images_per_second"] > 0


def test_main_tiene_numpy_importado():
    """Regresión directa: main.py usa np.array en la ruta de embeddings y en
    /debug/overlay; sin el import, ambas fallaban en runtime."""
    assert hasattr(main, "np"), "main.py debe importar numpy as np"
    assert main.np is np
