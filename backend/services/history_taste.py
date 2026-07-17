"""
history_taste.py — Fase H2: alimenta el taste model con las decisiones del
historial del fotógrafo.

Cada positiva (2-3★) es un ejemplo +1 y cada negativa (1★/banderín negro) un
-1, sobre su embedding CLIP. Usa TODAS las decisiones etiquetadas (no solo
pares dentro de ráfagas): más señal, más simple. Las 0★ (ambiguas) se excluyen.

Idempotente: cada foto alimenta el modelo una sola vez (flag fed_taste).
Requiere que sus embeddings ya estén en caché (correr embed_history antes).
"""
import logging
from pathlib import Path

from services.history_store import HistoryStore

logger = logging.getLogger(__name__)


def label_sign(label: str) -> int:
    """+1 seleccionada, -1 descartada."""
    return +1 if label == "positive" else -1


def feed_taste_from_history(store: HistoryStore | None = None,
                            limit: int | None = None) -> dict:
    from services import embedding_service
    from services.taste_model import taste_model

    if not embedding_service.is_available():
        return {"error": "CLIP no disponible", "fed": 0}

    store = store or HistoryStore()
    fed, sin_emb = 0, 0
    hechas: list[str] = []
    for path, label in store.unfed_labeled(limit):
        emb = embedding_service.embed_path(path, None)   # solo caché
        if emb is None:
            sin_emb += 1
            continue
        taste_model.add_example(emb, label_sign(label), "history",
                                event_dir=str(Path(path).parent))
        hechas.append(path)
        fed += 1

    if hechas:
        store.mark_fed(hechas)
    return {"fed": fed, "sin_embedding": sin_emb, "total_examples": taste_model.n_examples}
