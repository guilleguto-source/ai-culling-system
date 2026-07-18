"""
Tests de la Fase R: detectar cambios de Lightroom que no llegaron al archivo.

El caso que importa: el fotógrafo calificó en Lightroom pero no hizo Ctrl+S.
El catálogo dice 3★, el archivo dice 0★ → hay que avisarle ANTES de que
sincronice y no encuentre nada.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.catalog_diff import find_pending_changes, mensaje_para_usuario
from services.xmp_exporter import write_xmp
from tests.test_lightroom_sync import _minimal_jpeg


def _catalogo(lrcat: Path, fotos: list[tuple[str, int]], carpeta: str):
    """Catálogo mínimo con el esquema real: [(nombre_archivo, rating)]."""
    conn = sqlite3.connect(lrcat)
    conn.executescript("""
      CREATE TABLE AgLibraryRootFolder (id_local INTEGER PRIMARY KEY, absolutePath TEXT);
      CREATE TABLE AgLibraryFolder (id_local INTEGER PRIMARY KEY, pathFromRoot TEXT, rootFolder INTEGER);
      CREATE TABLE AgLibraryFile (id_local INTEGER PRIMARY KEY, baseName TEXT, extension TEXT, folder INTEGER);
      CREATE TABLE Adobe_images (id_local INTEGER PRIMARY KEY, rating REAL, pick REAL, captureTime TEXT, rootFile INTEGER);
      CREATE TABLE Adobe_imageDevelopSettings (id_local INTEGER PRIMARY KEY, image INTEGER, text TEXT);
    """)
    conn.execute("INSERT INTO AgLibraryRootFolder VALUES (1, ?)", (carpeta.replace("\\", "/") + "/",))
    conn.execute("INSERT INTO AgLibraryFolder VALUES (10, '', 1)")
    for i, (nombre, rating) in enumerate(fotos):
        base = nombre.rsplit(".", 1)[0]
        conn.execute("INSERT INTO AgLibraryFile VALUES (?, ?, 'jpg', 10)", (100 + i, base))
        conn.execute("INSERT INTO Adobe_images VALUES (?, ?, 0, '2025-03-01T10:00:00', ?)",
                     (1000 + i, rating, 100 + i))
    conn.commit()
    conn.close()


def test_detecta_cambios_sin_volcar(tmp_path):
    """Catálogo con 3★, archivo sin rating → pendiente."""
    jpg = _minimal_jpeg(tmp_path, "foto.jpg")
    lrcat = tmp_path / "cat.lrcat"
    _catalogo(lrcat, [("foto.jpg", 3)], str(tmp_path))

    res = find_pending_changes(str(lrcat), str(tmp_path))
    assert res["revisadas"] == 1 and res["pendientes"] == 1
    assert res["ejemplos"][0]["catalogo"] == 3 and res["ejemplos"][0]["archivo"] == 0
    assert "Ctrl+S" in mensaje_para_usuario(res)


def test_sin_diferencias_no_avisa(tmp_path):
    """Si el archivo ya tiene lo mismo que el catálogo, no hay nada que hacer."""
    jpg = _minimal_jpeg(tmp_path, "foto.jpg")
    write_xmp(str(jpg), "selected", 3, "", overwrite=True)
    lrcat = tmp_path / "cat.lrcat"
    _catalogo(lrcat, [("foto.jpg", 3)], str(tmp_path))

    res = find_pending_changes(str(lrcat), str(tmp_path))
    assert res["pendientes"] == 0
    assert mensaje_para_usuario(res) == ""


def test_ignora_fotos_de_otras_carpetas(tmp_path):
    """Solo importan las fotos del evento que se está sincronizando."""
    otra = tmp_path / "otro_evento"
    otra.mkdir()
    _minimal_jpeg(otra, "ajena.jpg")
    lrcat = tmp_path / "cat.lrcat"
    _catalogo(lrcat, [("ajena.jpg", 5)], str(otra))

    evento = tmp_path / "evento"
    evento.mkdir()
    res = find_pending_changes(str(lrcat), str(evento))
    assert res["revisadas"] == 0 and res["pendientes"] == 0
