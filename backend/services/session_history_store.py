"""
session_history_store.py — Persistencia y aprendizaje de retención real por tipo de evento.
Almacena el conteo inicial de la IA vs las fotos finales que el fotógrafo conservó para alimentar el Estimador Dinámico.
"""
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from services.app_paths import get_user_data_dir

logger = logging.getLogger(__name__)

THEORETICAL_RATES = {
    "few": 0.20,
    "standard": 0.35,
    "more": 0.50
}


class SessionHistoryStore:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = get_user_data_dir() / "session_history.db"
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_path TEXT,
                    event_type TEXT NOT NULL,
                    selectivity TEXT NOT NULL,
                    total_photos INTEGER NOT NULL,
                    ai_selected_count INTEGER NOT NULL,
                    final_kept_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def record_session(
        self,
        session_path: str,
        event_type: str,
        selectivity: str,
        total_photos: int,
        ai_selected_count: int,
        final_kept_count: int,
    ):
        """Registra una sesión finalizada con su resultado real."""
        if total_photos <= 0:
            return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO session_history (
                    session_path, event_type, selectivity, total_photos,
                    ai_selected_count, final_kept_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_path, event_type, selectivity, total_photos,
                ai_selected_count, final_kept_count, datetime.now().isoformat()
            ))
            conn.commit()
            logger.info(f"SessionHistoryStore: Sesión registrada para {event_type} ({final_kept_count}/{total_photos})")

    def get_estimate(self, total_photos: int, event_type: str, selectivity: str = "standard") -> Dict[str, Any]:
        """
        Calcula una estimación dinámica de fotos conservadas basándose en el historial real + modelo teórico.
        """
        theo_rate = THEORETICAL_RATES.get(selectivity, 0.35)
        
        if total_photos <= 0:
            return {
                "total_photos": 0,
                "min_photos": 0,
                "max_photos": 0,
                "estimated_percentage": round(theo_rate * 100),
                "is_calibrated": False,
                "samples_count": 0
            }

        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT total_photos, final_kept_count
                FROM session_history
                WHERE event_type = ?
                ORDER BY id DESC LIMIT 10
            """, (event_type,))
            rows = cur.fetchall()

        samples_count = len(rows)
        if samples_count == 0:
            # Sin historial: usar modelo puramente teórico
            effective_rate = theo_rate
            is_calibrated = False
        else:
            # Promedio ponderado real
            tot_sum = sum(r["total_photos"] for r in rows)
            kept_sum = sum(r["final_kept_count"] for r in rows)
            real_avg = kept_sum / max(tot_sum, 1)
            
            # Factor de mezcla alfa: más muestras = mayor peso a la historia real (hasta 80%)
            alpha = min(0.80, samples_count * 0.20)
            effective_rate = (1.0 - alpha) * theo_rate + alpha * real_avg
            is_calibrated = True

        # Rango con margen +/- 4%
        min_rate = max(0.05, effective_rate - 0.04)
        max_rate = min(0.95, effective_rate + 0.04)

        min_photos = max(1, int(round(total_photos * min_rate)))
        max_photos = max(min_photos, int(round(total_photos * max_rate)))

        return {
            "total_photos": total_photos,
            "min_photos": min_photos,
            "max_photos": max_photos,
            "estimated_percentage": round(effective_rate * 100),
            "is_calibrated": is_calibrated,
            "samples_count": samples_count
        }
