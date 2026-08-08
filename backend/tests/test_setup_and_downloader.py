import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from fastapi.testclient import TestClient
from main import app
from services.model_downloader import (
    MODEL_CATALOG,
    ModelSpec,
    get_models_status,
    get_all_states,
    _download_model,
    start_download,
)

client = TestClient(app)


def test_catalog_status(tmp_path):
    with patch("services.model_downloader.get_models_dir", return_value=tmp_path):
        status_list = get_models_status()
        assert len(status_list) == len(MODEL_CATALOG)
        
        # Como tmp_path está vacío, ninguno debe estar presente
        for item in status_list:
            assert item["present"] is False
            assert item["download_status"] in ("idle", "not_downloaded")
            
        # Simular que creamos un modelo requerido
        req_item = next(m for m in MODEL_CATALOG if m.required)
        (tmp_path / req_item.filename).write_bytes(b"dummy model data" * 100)
        
        status_list_after = get_models_status()
        req_status = next(s for s in status_list_after if s["id"] == req_item.id)
        assert req_status["present"] is True


def test_setup_endpoints(tmp_path):
    with patch("services.model_downloader.get_models_dir", return_value=tmp_path):
        res = client.get("/setup/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

        res_ready = client.get("/setup/required_ready")
        assert res_ready.status_code == 200
        assert "ready" in res_ready.json()
        assert res_ready.json()["ready"] is False


def test_download_mocked(tmp_path):
    fake_spec = ModelSpec(
        id="test_model",
        filename="test_model.bin",
        url="http://example.com/test_model.bin",
        size_mb=0.01,
        sha256=None,
        required=True,
        display_name="Test Model",
        description="Testing"
    )
    
    with patch("services.model_downloader.get_models_dir", return_value=tmp_path), \
         patch("urllib.request.urlopen") as mock_urlopen:
        
        mock_response = MagicMock()
        mock_response.headers.get.return_value = "1024"
        mock_response.read.side_effect = [b"a" * 512, b"b" * 512, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        _download_model(fake_spec)
        assert (tmp_path / "test_model.bin").exists()
        assert (tmp_path / "test_model.bin").read_bytes() == b"a" * 512 + b"b" * 512

