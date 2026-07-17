"""
history_store.py — Registros del bootstrap del historial (Fase H1).

Una fila por foto del historial del fotógrafo: su etiqueta según la convención
de rating, el revelado y el recorte crudos, y (más tarde) su escena. Es la
base que consumen el aprendizaje de gusto (H2), de revelado (J) y de recorte (K)
sin volver a leer el catálogo.
"""
import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "models" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    path TEXT PRIMARY KEY,
    label TEXT NOT NULL,            -- positive | negative | ignore | unreviewed
    rating INTEGER,
    pick INTEGER,
    capture_time TEXT,
    develop TEXT,                   -- json {campo crs: valor}
    crop TEXT,                      -- json {CropTop.. : valor}
    develop_extreme INTEGER,        -- 1 = edición extrema (fuera del estilo)
    source TEXT,                    -- catalog | xmp
    scene TEXT DEFAULT '',           -- lo rellena la Fase I
    fed_taste INTEGER DEFAULT 0      -- 1 = ya alimentó el taste model (H2)
);
"""


class HistoryStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(_SCHEMA)
        # Migración: fed_taste en bases creadas antes de la Fase H2.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(history)")}
        if "fed_taste" not in cols:
            conn.execute("ALTER TABLE history ADD COLUMN fed_taste INTEGER DEFAULT 0")
        return conn

    def upsert(self, rows: list[dict]) -> int:
        """Inserta o reemplaza registros del bootstrap. Devuelve cuántos."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO history "
                "(path, label, rating, pick, capture_time, develop, crop, develop_extreme, source) "
                "VALUES (:path, :label, :rating, :pick, :capture_time, :develop, :crop, :develop_extreme, :source)",
                [{**r, "develop": json.dumps(r["develop"]), "crop": json.dumps(r["crop"])} for r in rows],
            )
        return len(rows)

    def counts_by_label(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT label, COUNT(*) FROM history GROUP BY label").fetchall()
        return {label: n for label, n in rows}

    def count(self) -> int:
        with self._conn() as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM history").fetchone()
        return int(n)

    def paths_by_label(self, label: str) -> list[str]:
        with self._conn() as conn:
            return [r[0] for r in conn.execute(
                "SELECT path FROM history WHERE label = ?", (label,))]

    def set_scenes(self, scene_by_path: dict[str, str]) -> None:
        """Escribe la escena (Fase I) de cada foto ya etiquetada."""
        with self._conn() as conn:
            conn.executemany("UPDATE history SET scene = ? WHERE path = ?",
                             [(s, p) for p, s in scene_by_path.items()])

    def counts_by_scene(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT scene, COUNT(*) FROM history WHERE scene != '' GROUP BY scene").fetchall()
        return {s: n for s, n in rows}

    def develop_by_scene(self):
        """(path, scene, develop) de positivas con escena y revelado NO extremo
        — la base para aprender el estilo por escena (Fase J)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT path, scene, develop FROM history "
                "WHERE label='positive' AND scene!='' AND develop_extreme=0").fetchall()
        for path, scene, develop in rows:
            try:
                d = json.loads(develop) if develop else {}
            except json.JSONDecodeError:
                d = {}
            if d:
                yield path, scene, d

    def unfed_labeled(self, limit: int | None = None):
        """(path, label) de positivas/negativas que aún no alimentaron el taste
        model — para el aprendizaje de gusto (H2), idempotente."""
        sql = ("SELECT path, label FROM history "
               "WHERE label IN ('positive','negative') AND fed_taste=0")
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._conn() as conn:
            return conn.execute(sql).fetchall()

    def mark_fed(self, paths: list[str]) -> None:
        with self._conn() as conn:
            conn.executemany("UPDATE history SET fed_taste=1 WHERE path=?",
                             [(p,) for p in paths])

    def crops_by_scene(self):
        """(path, scene, crop) de positivas con escena y recorte — base de la
        Fase K. Solo recortes reales (HasCrop implícito: rectángulo presente)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT path, scene, crop FROM history "
                "WHERE label='positive' AND scene!='' AND crop!='' AND crop!='{}'").fetchall()
        for path, scene, crop in rows:
            try:
                c = json.loads(crop) if crop else {}
            except json.JSONDecodeError:
                c = {}
            if c:
                yield path, scene, c
