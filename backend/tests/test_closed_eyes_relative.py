"""
'Ojos cerrados' como criterio RELATIVO dentro de la ráfaga.

Medido sobre el evento real: el 97% de las fotos tienen al menos una cara con
ojos cerrados (una grupal de 3 niños = ~6 ojos; con ~20% de parpadeo, casi
siempre hay alguien). Marcar cualquier foto con >=1 ojo cerrado pintaba de
rojo casi todo el evento. Solo se marca la perdedora que tiene MÁS caras con
ojos cerrados que la ganadora de su grupo.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.decision import apply_decision_logic


def _rec(i):
    return SimpleNamespace(path=f"C:/ev/IMG_{i}.jpg", filename=f"IMG_{i}.jpg",
                           is_raw=False, error="", thumb_ai=None, linked_raw_path=None,
                           width=6000, height=4000)


def _an(i, closed=0, faces=3, away=0):
    # face_attrs (geometría cruda) + los conteos que en producción derivan de
    # ellos (analyze_photo) y refina el clasificador. El gate lee los conteos.
    attrs = []
    for _ in range(closed):
        attrs.append({"valid": True, "ear": 0.1, "blink": 0.8, "gaze_out": 0.0, "yaw": 0.0})
    for _ in range(away):
        attrs.append({"valid": True, "ear": 0.3, "blink": 0.1, "gaze_out": 0.8, "yaw": 0.0})
    while len(attrs) < faces:
        attrs.append({"valid": True, "ear": 0.3, "blink": 0.1, "gaze_out": 0.1, "yaw": 0.0})
    return PhotoAnalysis(index=i, path=f"C:/ev/IMG_{i}.jpg", scene_type="portrait",
                         face_attrs=attrs, blur_score=500.0,
                         closed_eyes_count=closed, looking_away_count=away,
                         face_count=faces, valid_face_count=faces,
                         any_closed_eyes=closed > 0)


SETTINGS = {"ratings_mapping": {
    "selected": {"stars": 2, "color": "Verde"}, "highlighted": {"stars": 3, "color": "Azul"},
    "blurry": {"stars": 0, "color": "Rojo"}, "closed_eyes": {"stars": 0, "color": "Rojo"},
    "duplicates": {"stars": 0, "color": ""},
}}
PREFS = {"selectivity_target": "standard", "detect_blurry": True, "detect_highlights": False}


def _run(analyses, rep_idx, prefs=None):
    idxs = [a.index for a in analyses]
    cluster = ImageCluster(0, "portrait", idxs, rep_idx)
    records = [_rec(i) for i in idxs]
    results, *_ = apply_decision_logic(
        records=records, analyses=analyses, clusters=[cluster],
        rep_scores={rep_idx: 1.0}, trash_flags=[False] * len(idxs),
        prefs=prefs or PREFS, settings=SETTINGS, develop_by_idx={},
    )
    return {r["filename"]: r["label"] for r in results}


def test_preferencia_apagada_no_marca():
    """La política vive en la decisión: con la casilla apagada no se marca,
    aunque el análisis SÍ midió los ojos (por eso activarla es instantáneo)."""
    analyses = [_an(0, closed=0), _an(1, closed=3)]
    off = {**PREFS, "detect_closed_eyes": False}
    assert _run(analyses, 0, prefs=off)["IMG_1.jpg"] == "duplicates"
    # la misma data, con la casilla encendida, sí marca
    assert _run(analyses, 0)["IMG_1.jpg"] == "closed_eyes"


def test_peor_del_grupo_se_marca_rojo():
    """La ganadora tiene 0 cerrados; la perdedora con 2 es la peor → closed_eyes."""
    labels = _run([_an(0, closed=0), _an(1, closed=2)], rep_idx=0)
    assert labels["IMG_0.jpg"] == "selected"
    assert labels["IMG_1.jpg"] == "closed_eyes"


def test_grupal_con_parpadeo_en_todas_no_pinta_las_perdedoras():
    """Regresión del 97%: si TODAS tienen alguien parpadeando, las perdedoras
    son duplicadas normales, no descartes rojos."""
    labels = _run([_an(0, closed=1), _an(1, closed=1), _an(2, closed=1)], rep_idx=0)
    assert labels["IMG_0.jpg"] == "selected"
    assert labels["IMG_1.jpg"] == "duplicates"
    assert labels["IMG_2.jpg"] == "duplicates"


def test_perdedora_mejor_que_la_ganadora_no_se_marca():
    """Si la perdedora tiene MENOS ojos cerrados que la ganadora, no es la peor."""
    labels = _run([_an(0, closed=2), _an(1, closed=0)], rep_idx=0)
    assert labels["IMG_1.jpg"] == "duplicates"


def test_ganadora_nunca_se_marca_por_ojos():
    labels = _run([_an(0, closed=3), _an(1, closed=3)], rep_idx=0)
    assert labels["IMG_0.jpg"] == "selected"


def test_sin_caras_no_aplica():
    labels = _run([_an(0, closed=0, faces=0), _an(1, closed=0, faces=0)], rep_idx=0)
    assert labels["IMG_1.jpg"] == "duplicates"


def test_cara_virada_tambien_descarta():
    """El fotógrafo descarta 'la peor: ojos cerrados O caras viradas'."""
    labels = _run([_an(0, away=0), _an(1, away=2)], rep_idx=0)
    assert labels["IMG_1.jpg"] == "closed_eyes"


def test_ojos_y_mirada_suman():
    """1 ojo cerrado + 1 virada es peor que la ganadora con 1 virada sola."""
    labels = _run([_an(0, closed=0, away=1), _an(1, closed=1, away=1)], rep_idx=0)
    assert labels["IMG_1.jpg"] == "closed_eyes"


def test_todas_viradas_por_igual_no_pinta():
    """Si en toda la ráfaga miran para otro lado, ninguna es 'la peor'."""
    labels = _run([_an(0, away=2), _an(1, away=2), _an(2, away=2)], rep_idx=0)
    assert labels["IMG_1.jpg"] == "duplicates"
    assert labels["IMG_2.jpg"] == "duplicates"
