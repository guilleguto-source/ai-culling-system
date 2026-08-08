"""Tests para el servicio de desempate ELO en RAM (Fase 3.4)."""
import pytest
from services.analysis import PhotoAnalysis
from services.elo_ranking import rank_burst_elo, compare_pair_advantage


def _mock_analysis(index=0, blur_score=100.0, aesthetic_score=0.5, closed_eyes=0, smiling=0, looking_away=0):
    a = PhotoAnalysis(index=index, path=f"photo_{index}.jpg")
    a.blur_score = blur_score
    a.aesthetic_score = aesthetic_score
    a.closed_eyes_count = closed_eyes
    a.smiling_count = smiling
    a.looking_away_count = looking_away
    a.valid_face_count = 1
    return a


def test_elo_single_candidate():
    ranked, elo, reason = rank_burst_elo([0], [_mock_analysis()], {0: 0.8})
    assert ranked == [0]
    assert elo[0] == 1500.0


def test_elo_tiebreak_by_smile():
    # Dos fotos con exactamente el mismo base_score y nitidez, pero foto 1 tiene sonrisa
    a0 = _mock_analysis(blur_score=200.0, smiling=0)
    a1 = _mock_analysis(blur_score=200.0, smiling=1)

    analyses = [a0, a1]
    scores = {0: 0.850, 1: 0.851}

    ranked, elo, reason = rank_burst_elo([0, 1], analyses, scores)
    assert ranked[0] == 1
    assert elo[1] > elo[0]
    assert "sonrisa" in reason or "expresión" in reason


def test_elo_tiebreak_by_sharpness():
    # Dos fotos con el mismo base_score, pero foto 0 tiene mucho mejor nitidez
    a0 = _mock_analysis(blur_score=450.0)
    a1 = _mock_analysis(blur_score=150.0)

    analyses = [a0, a1]
    scores = {0: 0.800, 1: 0.801}

    ranked, elo, reason = rank_burst_elo([0, 1], analyses, scores)
    assert ranked[0] == 0
    assert elo[0] > elo[1]
    assert "nitidez" in reason.lower() or "estético" in reason.lower()


def test_elo_multi_candidate_tournament():
    # 4 fotos en ráfaga reñida
    analyses = [
        _mock_analysis(blur_score=300.0, smiling=0),
        _mock_analysis(blur_score=320.0, smiling=1),  # Debería ganar (sonrisa + buena nitidez)
        _mock_analysis(blur_score=100.0, closed_eyes=1), # Peor
        _mock_analysis(blur_score=250.0, smiling=0),
    ]
    scores = {0: 0.80, 1: 0.81, 2: 0.79, 3: 0.80}

    ranked, elo, _ = rank_burst_elo([0, 1, 2, 3], analyses, scores)
    assert ranked[0] == 1
    assert ranked[-1] == 2
