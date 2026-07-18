"""
Tests de la Fase O: respaldo previo al export y deshacer.

Lo crítico: tras deshacer, el rating del fotógrafo debe volver a ser EXACTAMENTE
el que tenía. Y una foto que no tenía XMP no debe quedar con nuestras marcas.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import undo_export
from services.xmp_exporter import write_xmp, read_raw_packet
from services.xmp_reader import read_xmp
from tests.test_lightroom_sync import _minimal_jpeg


@pytest.fixture(autouse=True)
def _isolar_undo(tmp_path, monkeypatch):
    """Los respaldos van a un temporal, no a models/undo real."""
    monkeypatch.setattr(undo_export, "UNDO_DIR", tmp_path / "undo")


def test_roundtrip_restaura_el_rating_previo(tmp_path):
    jpg = _minimal_jpeg(tmp_path)
    # El fotógrafo ya tenía su criterio puesto
    write_xmp(str(jpg), "selected", 3, "Azul", overwrite=True)
    previo = read_xmp(str(jpg))

    undo_export.capture_previous_state(str(tmp_path), [str(jpg)])

    # El culling lo pisa
    write_xmp(str(jpg), "duplicates", 1, "Roja", overwrite=True)
    assert read_xmp(str(jpg))["stars"] == 1

    res = undo_export.restore_previous_state(str(tmp_path))
    assert res["restauradas"] == 1
    assert read_xmp(str(jpg)) == previo        # exactamente como estaba


def test_respaldo_es_byte_a_byte(tmp_path):
    jpg = _minimal_jpeg(tmp_path)
    write_xmp(str(jpg), "selected", 2, "Verde", overwrite=True)
    original = read_raw_packet(str(jpg))

    undo_export.capture_previous_state(str(tmp_path), [str(jpg)])
    write_xmp(str(jpg), "blurry", 1, "Roja", overwrite=True)
    undo_export.restore_previous_state(str(tmp_path))

    assert read_raw_packet(str(jpg)) == original


def test_foto_sin_xmp_previo_no_queda_con_nuestras_marcas(tmp_path):
    jpg = _minimal_jpeg(tmp_path)
    assert read_raw_packet(str(jpg)) is None       # arranca limpia

    undo_export.capture_previous_state(str(tmp_path), [str(jpg)])
    write_xmp(str(jpg), "selected", 4, "Verde", overwrite=True)
    undo_export.restore_previous_state(str(tmp_path))

    d = read_xmp(str(jpg))
    # En JPEG el segmento no se puede quitar: queda neutro, sin rating ni color.
    assert d is None or (d["stars"] == 0 and not d["color"])


def test_sin_respaldo_avisa(tmp_path):
    assert not undo_export.has_backup(str(tmp_path))
    res = undo_export.restore_previous_state(str(tmp_path))
    assert res["restauradas"] == 0 and "error" in res


def test_capture_reporta_cuantas_tenian_xmp(tmp_path):
    a, b = _minimal_jpeg(tmp_path, "a.jpg"), _minimal_jpeg(tmp_path, "b.jpg")
    write_xmp(str(a), "selected", 2, "Verde", overwrite=True)
    res = undo_export.capture_previous_state(str(tmp_path), [str(a), str(b)])
    assert res == {"respaldadas": 2, "con_xmp_previo": 1}
