import pytest


@pytest.fixture(autouse=True)
def _isolate_exports(tmp_path, monkeypatch):
    """
    Aísla la carpeta de snapshots de export por test: sin esto, los tests que
    corren el pipeline escriben en la carpeta REAL (backend/models/exports/) y
    contaminan el recordatorio de sincronización con eventos de prueba.
    """
    from services import export_snapshot
    monkeypatch.setattr(export_snapshot, "EXPORTS_DIR", tmp_path / "exports")
