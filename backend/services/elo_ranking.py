"""
elo_ranking.py — Motor de desempate ultrarrápido en RAM mediante torneos ELO (Fase 3.4).

Cuando las mejores fotos de una ráfaga sobreviven los gates técnicos y tienen un
margen de score muy estrecho (<= 2%), este servicio ejecuta un torneo 1vs1 round-robin
en memoria para desempatar de forma determinista y matemáticamente sólida.
"""
from __future__ import annotations
import math
from typing import Any
from services.analysis import PhotoAnalysis


K_FACTOR = 32.0
INITIAL_ELO = 1500.0


def _sigmoid(x: float) -> float:
    """Función sigmoide estable para calcular probabilidad de victoria."""
    try:
        return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def compare_pair_advantage(
    analysis_a: PhotoAnalysis | None,
    analysis_b: PhotoAnalysis | None,
    score_a: float,
    score_b: float,
    taste_diff: float = 0.0,
) -> float:
    """
    Calcula la ventaja relativa de A sobre B en una escala normalizada [-5.0, 5.0].
    Pondera diferenciales de ojos, sonrisa, nitidez, score estético y afinidad con el modelo de gustos.
    """
    if analysis_a is None or analysis_b is None:
        return (score_a - score_b) * 10.0

    delta = 0.0

    # 1. Diferencial de ojos cerrados (penalización severa)
    closed_diff = analysis_b.closed_eyes_count - analysis_a.closed_eyes_count
    delta += closed_diff * 1.8

    # 2. Diferencial de sonrisas / expresión
    smile_diff = analysis_a.smiling_count - analysis_b.smiling_count
    delta += smile_diff * 1.2

    # 3. Diferencial de mirada a cámara
    gaze_diff = analysis_b.looking_away_count - analysis_a.looking_away_count
    delta += gaze_diff * 0.8

    # 4. Nitidez relativa (blur_score)
    blur_a = getattr(analysis_a, "blur_score", 0.0) or 0.0
    blur_b = getattr(analysis_b, "blur_score", 0.0) or 0.0
    max_blur = max(blur_a, blur_b, 1.0)
    blur_diff = (blur_a - blur_b) / max_blur
    delta += blur_diff * 1.5

    # 5. Score estético global
    aes_a = getattr(analysis_a, "aesthetic_score", 0.5) or 0.5
    aes_b = getattr(analysis_b, "aesthetic_score", 0.5) or 0.5
    delta += (aes_a - aes_b) * 2.0

    # 6. Afinidad con Taste Model si existe
    delta += taste_diff * 1.5

    return delta


def rank_burst_elo(
    candidate_indices: list[int],
    analyses: list[PhotoAnalysis],
    base_scores: dict[int, float],
    taste_diffs: dict[tuple[int, int], float] | None = None,
) -> tuple[list[int], dict[int, float], str]:
    """
    Ejecuta un torneo ELO round-robin entre los índices candidatos.
    Retorna:
      - indices_ordenados: lista de índices ordenados de mayor a menor ELO
      - elo_scores: dict con el puntaje ELO final de cada índice
      - tie_break_reason: explicación legible del desempate
    """
    if not candidate_indices:
        return [], {}, ""

    if len(candidate_indices) == 1:
        idx = candidate_indices[0]
        return [idx], {idx: INITIAL_ELO}, ""

    elo: dict[int, float] = {idx: INITIAL_ELO for idx in candidate_indices}
    wins: dict[int, int] = {idx: 0 for idx in candidate_indices}
    n = len(candidate_indices)

    # Torneo Round-Robin en memoria
    for i in range(n):
        idx_a = candidate_indices[i]
        a_anal = analyses[idx_a] if idx_a < len(analyses) else None
        s_a = base_scores.get(idx_a, 0.0)

        for j in range(i + 1, n):
            idx_b = candidate_indices[j]
            b_anal = analyses[idx_b] if idx_b < len(analyses) else None
            s_b = base_scores.get(idx_b, 0.0)

            t_diff = 0.0
            if taste_diffs:
                t_diff = taste_diffs.get((idx_a, idx_b), -taste_diffs.get((idx_b, idx_a), 0.0))

            adv = compare_pair_advantage(a_anal, b_anal, s_a, s_b, t_diff)
            # Probabilidad real del matchup basada en métricas
            actual_score_a = _sigmoid(adv)
            actual_score_b = 1.0 - actual_score_a

            # Probabilidad esperada basada en el ELO actual
            expected_a = 1.0 / (1.0 + 10.0 ** ((elo[idx_b] - elo[idx_a]) / 400.0))
            expected_b = 1.0 - expected_a

            # Actualización ELO
            elo[idx_a] += K_FACTOR * (actual_score_a - expected_a)
            elo[idx_b] += K_FACTOR * (actual_score_b - expected_b)

            if actual_score_a > 0.5:
                wins[idx_a] += 1
            elif actual_score_b > 0.5:
                wins[idx_b] += 1

    # Ordenar candidatos por ELO final descendente
    ranked = sorted(candidate_indices, key=lambda idx: elo[idx], reverse=True)
    winner = ranked[0]
    w_anal = analyses[winner] if winner < len(analyses) else None

    # Construir motivo específico
    if w_anal and w_anal.smiling_count > 0:
        reason = "✔ Desempate ELO: mejor expresión facial y sonrisa en ráfaga reñida"
    elif w_anal and w_anal.closed_eyes_count == 0 and any(
        analyses[i].closed_eyes_count > 0 for i in candidate_indices if i < len(analyses) and i != winner
    ):
        reason = "✔ Desempate ELO: todos con ojos abiertos"
    else:
        reason = "✔ Desempate ELO: mayor nitidez relativa y balance estético"

    return ranked, elo, reason
