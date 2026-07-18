"""
Tests de la Fase Q: pares de gusto dentro de la ráfaga.

La regla que importa: solo se aprende de ráfagas REVISADAS (con al menos una
2★+). En una ráfaga sin ninguna estrella no se sabe si el fotógrafo la miró,
así que sus 0★ no son perdedoras legítimas.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.history_store import HistoryStore
from services.history_taste import build_burst_pairs, _pares_de_rafaga


def _emb(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.normal(0, 1, 16).astype(np.float32)
    return v / np.linalg.norm(v)


def _row(path, label, capture):
    return {"path": path, "label": label, "rating": 2, "pick": 0,
            "capture_time": capture, "develop": {}, "crop": {},
            "develop_extreme": 0, "source": "catalog"}


# --- Reglas de la ráfaga ---

def test_rafaga_sin_positiva_no_genera_pares():
    rafaga = [("a.jpg", "unreviewed", _emb(1)), ("b.jpg", "negative", _emb(2))]
    assert _pares_de_rafaga(rafaga) == []


def test_rafaga_revisada_empareja_ganadora_con_perdedoras():
    rafaga = [("g.jpg", "positive", _emb(1)),
              ("p1.jpg", "unreviewed", _emb(2)),
              ("p2.jpg", "negative", _emb(3))]
    pares = _pares_de_rafaga(rafaga)
    assert len(pares) == 2
    assert all(g[1] == "positive" for g, _ in pares)
    assert {p[0] for _, p in pares} == {"p1.jpg", "p2.jpg"}


# --- Reconstrucción de ráfagas ---

def test_separa_rafagas_por_similitud(tmp_path):
    """Fotos visualmente distintas no son la misma ráfaga aunque estén juntas."""
    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([
        _row("/ev/a.jpg", "positive", "2025-03-01T10:00:00"),
        _row("/ev/b.jpg", "unreviewed", "2025-03-01T10:00:05"),   # misma ráfaga
        _row("/ev/c.jpg", "unreviewed", "2025-03-01T10:00:10"),   # otra escena
    ])
    igual, distinta = _emb(1), _emb(99)
    embs = {"/ev/a.jpg": igual, "/ev/b.jpg": igual, "/ev/c.jpg": distinta}

    pares = build_burst_pairs(s, embed_fn=lambda p: embs[p])
    # a y b son la misma ráfaga (a gana); c queda en otra ráfaga sin positiva
    assert len(pares) == 1
    assert pares[0][0][0] == "/ev/a.jpg" and pares[0][1][0] == "/ev/b.jpg"


def test_separa_rafagas_por_hueco_temporal(tmp_path):
    """Mismo encuadre pero horas después: no es la misma ráfaga."""
    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([
        _row("/ev/a.jpg", "positive", "2025-03-01T10:00:00"),
        _row("/ev/b.jpg", "unreviewed", "2025-03-01T14:00:00"),
    ])
    igual = _emb(1)
    pares = build_burst_pairs(s, embed_fn=lambda _p: igual)
    assert pares == []


def test_fechas_con_y_sin_zona_horaria_conviven(tmp_path):
    """El catálogo mezcla ambas; ordenarlas no debe reventar."""
    from services.history_taste import _ts
    con_tz, sin_tz = _ts("2025-03-01T10:00:00+00:00"), _ts("2025-03-01T11:00:00")
    assert con_tz is not None and sin_tz is not None
    assert sin_tz > con_tz          # comparables entre sí
    assert _ts("basura") is None

    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([
        _row("/ev/a.jpg", "positive", "2025-03-01T10:00:00+00:00"),
        _row("/ev/b.jpg", "unreviewed", "2025-03-01T10:00:05"),
    ])
    igual = _emb(1)
    build_burst_pairs(s, embed_fn=lambda _p: igual)   # no debe lanzar


def test_sin_embedding_se_omite(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([_row("/ev/a.jpg", "positive", "2025-03-01T10:00:00")])
    assert build_burst_pairs(s, embed_fn=lambda _p: None) == []
