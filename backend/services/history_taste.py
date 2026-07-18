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


# --- Fase Q: pares dentro de la ráfaga ---
# El gusto absoluto ("elegida vs descarte" sobre todo el catálogo) da AUC 0,69:
# las 1★ son fotos que el fotógrafo editó y después bajó, visualmente casi
# idénticas a las que conservó. La tarea REAL es "de estas casi iguales, cuál",
# así que se aprende comparando dentro de la misma ráfaga.

BURST_SIM = 0.90        # similitud coseno mínima para considerar misma ráfaga
BURST_GAP_S = 30        # y como máximo este hueco temporal
MAX_LOSERS_PER_WINNER = 3   # acota la explosión combinatoria


def _ts(valor: str):
    """
    Fecha de captura → datetime NAIVE. El catálogo mezcla fechas con y sin zona
    horaria; si no se normaliza, ordenarlas revienta ("can't compare
    offset-naive and offset-aware datetimes").
    """
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _misma_rafaga(emb_a, ts_a, emb_b, ts_b) -> bool:
    import numpy as np
    if emb_a is None or emb_b is None:
        return False
    if ts_a and ts_b and abs((ts_b - ts_a).total_seconds()) > BURST_GAP_S:
        return False
    return float(np.dot(emb_a, emb_b)) >= BURST_SIM


def _pares_de_rafaga(rafaga: list[tuple]) -> list[tuple]:
    """
    De una ráfaga saca pares (ganadora, perdedora). Solo se usan ráfagas
    REVISADAS — las que tienen al menos una 2★+, prueba de que el fotógrafo la
    miró. Ahí una 0★ es una perdedora legítima; en una ráfaga sin ninguna
    estrella no se sabe si la vio siquiera.
    """
    ganadoras = [r for r in rafaga if r[1] == "positive"]
    if not ganadoras:
        return []
    perdedoras = [r for r in rafaga if r[1] in ("negative", "unreviewed")]
    return [(g, p) for g in ganadoras for p in perdedoras[:MAX_LOSERS_PER_WINNER]]


def build_burst_pairs(store: HistoryStore | None = None, embed_fn=None) -> list[tuple]:
    """
    Reconstruye las ráfagas del historial (por similitud visual + cercanía
    temporal dentro de la misma carpeta) y devuelve los pares comparables.
    `embed_fn` se inyecta en los tests; por defecto usa la caché de CLIP.
    """
    from collections import defaultdict

    if embed_fn is None:
        from services import embedding_service
        embed_fn = lambda p: embedding_service.embed_path(p, None)

    store = store or HistoryStore()
    por_carpeta = defaultdict(list)
    for path, label, capture in store.rows_for_bursts():
        por_carpeta[str(Path(path).parent)].append((path, label, _ts(capture)))

    pares: list[tuple] = []
    for items in por_carpeta.values():
        items.sort(key=lambda x: (x[2] is None, x[2]))
        rafaga: list[tuple] = []
        prev_emb = prev_ts = None
        for path, label, ts in items:
            emb = embed_fn(path)
            if emb is None:
                continue
            if rafaga and _misma_rafaga(prev_emb, prev_ts, emb, ts):
                rafaga.append((path, label, emb))
            else:
                pares.extend(_pares_de_rafaga(rafaga))
                rafaga = [(path, label, emb)]
            prev_emb, prev_ts = emb, ts
        pares.extend(_pares_de_rafaga(rafaga))
    return pares


def feed_pairwise_from_history(store: HistoryStore | None = None) -> dict:
    """Alimenta el gusto con pares ganadora/perdedora de cada ráfaga revisada."""
    from services import embedding_service
    from services.taste_model import taste_model

    if not embedding_service.is_available():
        return {"error": "CLIP no disponible", "pares": 0}

    pares = build_burst_pairs(store)
    for (gp, _gl, ge), (pp, _pl, pe) in pares:
        taste_model.learn_preference(ge, pe, source="history-pair",
                                     event_dir=str(Path(gp).parent))
    return {"pares": len(pares), "total_examples": taste_model.n_examples}


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
