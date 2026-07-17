"""
Tests de la Fase H1: bootstrap del historial.

Cubre la convención de selección del usuario, el parseo del blob de revelado
del catálogo, el filtro de fecha, y la lectura de revelado/recorte desde XMP.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.history_bootstrap import classify, is_extreme_develop, bootstrap_from_catalog
from services.history_store import HistoryStore
from services.lr_catalog import _parse_blob, DEVELOP_FIELDS, CROP_FIELDS


# --- Convención de rating ---

def test_convencion_de_seleccion():
    assert classify(2, 0) == "positive"       # interesante
    assert classify(3, 0) == "positive"       # highlight
    assert classify(1, 0) == "negative"       # bajada al editar
    assert classify(0, -1) == "negative"      # banderín negro
    assert classify(4, 0) == "ignore"         # marcador, no calidad
    assert classify(5, 0) == "ignore"
    assert classify(0, 0) == "unreviewed"     # sin revisar
    # El banderín negro manda aunque haya estrellas
    assert classify(2, -1) == "negative"


def test_edicion_extrema_se_marca():
    assert is_extreme_develop({"Exposure2012": 1.5})
    assert is_extreme_develop({"Exposure2012": -1.2})
    assert not is_extreme_develop({"Exposure2012": 0.4})
    assert not is_extreme_develop({})


# --- Parseo del blob de revelado ---

def test_parse_blob_revelado_y_recorte():
    blob = ("s = { Exposure2012 = 0.35,\nContrast2012 = -15,\nTemperature = 5193,\n"
            "CropTop = 0.032,\nCropAngle = 0.14,\nConvertToGrayscale = false }")
    dev = _parse_blob(blob, DEVELOP_FIELDS)
    crop = _parse_blob(blob, CROP_FIELDS)
    assert dev["Exposure2012"] == 0.35 and dev["Contrast2012"] == -15.0
    assert crop["CropTop"] == 0.032 and crop["CropAngle"] == 0.14
    assert _parse_blob(None, DEVELOP_FIELDS) == {}


# --- Lectura del catálogo (SQLite sintético con el esquema real) ---

def _fake_lrcat(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript("""
      CREATE TABLE AgLibraryRootFolder (id_local INTEGER PRIMARY KEY, absolutePath TEXT);
      CREATE TABLE AgLibraryFolder (id_local INTEGER PRIMARY KEY, pathFromRoot TEXT, rootFolder INTEGER);
      CREATE TABLE AgLibraryFile (id_local INTEGER PRIMARY KEY, baseName TEXT, extension TEXT, folder INTEGER);
      CREATE TABLE Adobe_images (id_local INTEGER PRIMARY KEY, rating REAL, pick REAL, captureTime TEXT, rootFile INTEGER);
      CREATE TABLE Adobe_imageDevelopSettings (id_local INTEGER PRIMARY KEY, image INTEGER, text TEXT);
    """)
    conn.execute("INSERT INTO AgLibraryRootFolder VALUES (1, 'C:/Fotos/')")
    conn.execute("INSERT INTO AgLibraryFolder VALUES (10, '2025-03/', 1)")
    conn.execute("INSERT INTO AgLibraryFile VALUES (100, 'IMG_1', 'JPG', 10)")
    conn.execute("INSERT INTO AgLibraryFile VALUES (101, 'IMG_2', 'JPG', 10)")
    conn.execute("INSERT INTO AgLibraryFile VALUES (102, 'IMG_OLD', 'JPG', 10)")
    # IMG_1: 2★, revelado normal ; IMG_2: negro ; IMG_OLD: fuera de fecha
    conn.execute("INSERT INTO Adobe_images VALUES (1000, 2, 0, '2025-03-10T10:00:00', 100)")
    conn.execute("INSERT INTO Adobe_images VALUES (1001, 0, -1, '2025-03-11T10:00:00', 101)")
    conn.execute("INSERT INTO Adobe_images VALUES (1002, 3, 0, '2024-11-01T10:00:00', 102)")
    conn.execute("INSERT INTO Adobe_imageDevelopSettings VALUES (1, 1000, 's = { Exposure2012 = 0.3, CropTop = 0.05 }')")
    conn.commit()
    conn.close()


def test_lee_catalogo_y_filtra_fecha(tmp_path):
    lrcat = tmp_path / "cat.lrcat"
    _fake_lrcat(lrcat)
    store = HistoryStore(db_path=tmp_path / "history.db")
    res = bootstrap_from_catalog(str(lrcat), since="2025-02-01", dry_run=False, store=store)

    # IMG_OLD (2024) queda fuera por fecha
    assert res["total"] == 2
    assert res["por_etiqueta"] == {"positive": 1, "negative": 1}
    assert res["con_revelado"] == 1 and res["con_recorte"] == 1
    assert store.counts_by_label() == {"positive": 1, "negative": 1}


def test_dry_run_no_persiste(tmp_path):
    lrcat = tmp_path / "cat.lrcat"
    _fake_lrcat(lrcat)
    store = HistoryStore(db_path=tmp_path / "history.db")
    res = bootstrap_from_catalog(str(lrcat), dry_run=True, store=store)
    assert res["total"] == 2
    assert store.count() == 0    # dry-run no escribe
