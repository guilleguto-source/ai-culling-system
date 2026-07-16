"""
calibration_store.py — Verdad de campo del fotógrafo sobre caras (Fase G2).

Sirve para dos cosas, en este orden:
  1. MEDIR: comparar lo que dice el detector (`predicted`) contra lo que dice
     el fotógrafo (`value`) → precisión real sobre SUS fotos, con números.
  2. ENTRENAR (G3): el embedding CLIP del recorte queda guardado, así que si
     la geometría no basta se entrena un clasificador sin re-etiquetar nada.

Se guarda `predicted` junto a `value` para poder calcular el acuerdo sin
re-analizar, y para detectar deriva si cambian los umbrales del detector.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "models" / "calibration.db"

# Atributos y sus valores válidos (ver spec 2026-07-16-calibracion-design).
# "alegría/felicidad" NO se etiqueta: en escala absoluta los datos salen
# inconsistentes con el propio usuario; esa señal la captura el duelo.
ATTRIBUTES = {
    "eyes": ["abiertos", "cerrados", "entrecerrados"],
    "gaze": ["camara", "fuera"],
    "mouth": ["sonrisa", "neutra", "hablando"],
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS face_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    face_index INTEGER NOT NULL,
    face_bbox TEXT,
    embedding BLOB,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    predicted TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(photo_path, face_index, attribute)
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA)
    except sqlite3.DatabaseError:
        conn.close()
        raise
    return conn


class CalibrationStore:
    def __init__(self, db_path: Path | None = None):
        # Se resuelve en la LLAMADA, no al importar: un default `= DB_PATH`
        # congela la ruta y hace que los tests escriban en la base real.
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _conn(self) -> sqlite3.Connection:
        try:
            return _connect(self.db_path)
        except sqlite3.DatabaseError as e:
            logger.error(f"calibration.db corrupta ({e}); se renombra a .bak y se recrea.")
            bak = self.db_path.with_suffix(".db.bak")
            bak.unlink(missing_ok=True)
            self.db_path.rename(bak)
            return _connect(self.db_path)

    def add_label(self, photo_path: str, face_index: int, attribute: str,
                  value: str, predicted: str = "", face_bbox: list | None = None,
                  embedding: np.ndarray | None = None) -> None:
        """Guarda (o reemplaza) la etiqueta del usuario para una cara."""
        if attribute not in ATTRIBUTES:
            raise ValueError(f"atributo desconocido: {attribute}")
        if value not in ATTRIBUTES[attribute]:
            raise ValueError(f"valor '{value}' no válido para {attribute}")
        blob = np.asarray(embedding, dtype=np.float32).tobytes() if embedding is not None else None
        import json
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO face_labels "
                "(photo_path, face_index, face_bbox, embedding, attribute, value, predicted, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (photo_path, face_index, json.dumps(face_bbox or []), blob,
                 attribute, value, predicted,
                 datetime.now(timezone.utc).isoformat()),
            )

    def labeled_faces(self) -> set[tuple[str, int]]:
        """(photo_path, face_index) ya etiquetados — para no volver a preguntar."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT photo_path, face_index FROM face_labels").fetchall()
        return {(r[0], r[1]) for r in rows}

    def count(self, attribute: str | None = None) -> int:
        with self._conn() as conn:
            if attribute:
                (n,) = conn.execute(
                    "SELECT COUNT(*) FROM face_labels WHERE attribute = ?",
                    (attribute,)).fetchone()
            else:
                (n,) = conn.execute("SELECT COUNT(*) FROM face_labels").fetchone()
        return int(n)

    def agreement(self, attribute: str) -> dict:
        """
        Precisión REAL del detector sobre las fotos del usuario:
        cuántas veces `predicted` coincidió con lo que él dijo.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT value, predicted FROM face_labels "
                "WHERE attribute = ? AND predicted != ''", (attribute,)).fetchall()
        if not rows:
            return {"total": 0, "aciertos": 0, "precision": None}
        aciertos = sum(1 for v, p in rows if v == p)
        return {"total": len(rows), "aciertos": aciertos,
                "precision": round(aciertos / len(rows), 3)}

    def training_set(self, attribute: str, embedding_dim: int) -> tuple[np.ndarray, list[str]]:
        """(X, y) con los ejemplos que tienen embedding — para G3."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT embedding, value FROM face_labels "
                "WHERE attribute = ? AND embedding IS NOT NULL", (attribute,)).fetchall()
        rows = [(b, v) for b, v in rows if b and len(b) == embedding_dim * 4]
        if not rows:
            return np.empty((0, embedding_dim), dtype=np.float32), []
        X = np.stack([np.frombuffer(b, dtype=np.float32) for b, _ in rows])
        return X, [v for _, v in rows]
