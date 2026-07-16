"""
taste_store.py — Almacén persistente de ejemplos de gusto del usuario.
Cada ejemplo es un embedding visual + label (+1 elegida / -1 rechazada),
con su origen (duelo o corrección en Lightroom) para trazabilidad.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "models" / "taste_examples.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    embedding BLOB NOT NULL,
    label INTEGER NOT NULL,            -- +1 elegida, -1 rechazada
    source TEXT NOT NULL,              -- 'duel' | 'lightroom'
    event_dir TEXT,
    created_at TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    model_version TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA)
    except sqlite3.DatabaseError:
        # Cerrar SIEMPRE antes de propagar: en Windows un archivo abierto
        # no puede renombrarse (recuperación de DB corrupta).
        conn.close()
        raise
    return conn


class TasteStore:
    def __init__(self, db_path: Path | None = None):
        # Se resuelve en la LLAMADA, no al importar (un default `= DB_PATH`
        # congela la ruta e ignora cualquier monkeypatch en tests).
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _conn(self) -> sqlite3.Connection:
        try:
            return _connect(self.db_path)
        except sqlite3.DatabaseError as e:
            # DB corrupta: renombrar a .bak y recrear vacía
            logger.error(f"Base de ejemplos corrupta ({e}); se renombra a .bak y se recrea.")
            bak = self.db_path.with_suffix(".db.bak")
            bak.unlink(missing_ok=True)
            self.db_path.rename(bak)
            return _connect(self.db_path)

    def add_example(
        self,
        embedding: np.ndarray,
        label: int,
        source: str,
        event_dir: str = "",
        model_version: str = "",
    ) -> None:
        vec = np.asarray(embedding, dtype=np.float32)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO examples (embedding, label, source, event_dir, created_at, embedding_dim, model_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    vec.tobytes(),
                    int(label),
                    source,
                    event_dir,
                    datetime.now(timezone.utc).isoformat(),
                    vec.shape[0],
                    model_version,
                ),
            )

    def load_examples(
        self, embedding_dim: int, model_version: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Carga (X, y) con solo los ejemplos compatibles con el modelo de
        embeddings actual. Los incompatibles se conservan pero no se usan.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT embedding, label FROM examples "
                "WHERE embedding_dim = ? AND model_version = ? ORDER BY id",
                (embedding_dim, model_version),
            ).fetchall()
        if not rows:
            return np.empty((0, embedding_dim), dtype=np.float32), np.empty(0, dtype=np.int64)
        X = np.stack([np.frombuffer(blob, dtype=np.float32) for blob, _ in rows])
        y = np.array([label for _, label in rows], dtype=np.int64)
        return X, y

    def count(self, embedding_dim: int, model_version: str) -> int:
        with self._conn() as conn:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM examples WHERE embedding_dim = ? AND model_version = ?",
                (embedding_dim, model_version),
            ).fetchone()
        return int(n)
