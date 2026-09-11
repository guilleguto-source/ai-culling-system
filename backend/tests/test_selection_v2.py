import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.decision import apply_decision_logic, trim_excess_to_target
from services.face_identity import rank_vip_identities


def _make_rec(idx: int, width: int = 6000, height: int = 4000):
    return SimpleNamespace(
        path=f"C:/test/IMG_{idx:04d}.jpg",
        filename=f"IMG_{idx:04d}.jpg",
        is_raw=False,
        error="",
        thumb_ai=None,
        linked_raw_path=None,
        width=width,
        height=height,
    )


def _make_analysis(idx: int, blur: float = 400.0, aesthetic: float = 0.5):
    return PhotoAnalysis(
        index=idx,
        path=f"C:/test/IMG_{idx:04d}.jpg",
        scene_type="portrait",
        face_attrs=[],
        blur_score=blur,
        aesthetic_score=aesthetic,
        closed_eyes_count=0,
        looking_away_count=0,
        face_count=1,
        valid_face_count=1,
    )


SETTINGS = {
    "ratings_mapping": {
        "selected": {"stars": 2, "color": "Verde"},
        "highlighted": {"stars": 3, "color": "Azul"},
        "alternative": {"stars": 1, "color": ""},
        "recommended": {"stars": 1, "color": "Amarillo"},
        "blurry": {"stars": 0, "color": "Rojo"},
        "closed_eyes": {"stars": 0, "color": ""},
        "duplicates": {"stars": 0, "color": ""},
    }
}


def test_rank_vip_identities():
    """Verifica que las identidades más frecuentes son catalogadas como VIP."""
    identidades = {
        0: [10, 20],
        1: [10],
        2: [10, 20],
        3: [10],
        4: [20],
        5: [30],
        6: [40],
    }
    # 10 aparece 4 veces, 20 aparece 3 veces, 30 y 40 1 vez
    vips = rank_vip_identities(identidades, top_n=2)
    assert vips == {10, 20}


def test_supervivencia_obligatoria_bajo_score():
    """Un cluster cuyo score máximo es bajo (ej. 0.25 nocturno) SIEMPRE tiene 1 foto seleccionada."""
    records = [_make_rec(0), _make_rec(1)]
    analyses = [_make_analysis(0, blur=150.0), _make_analysis(1, blur=100.0)]
    clusters = [ImageCluster(0, "portrait", [0, 1], representative_index=0)]
    scores = {0: 0.25, 1: 0.15}  # muy por debajo del standard 0.42

    results, demoted, final_selected, highlights = apply_decision_logic(
        records=records,
        analyses=analyses,
        clusters=clusters,
        rep_scores=scores,
        trash_flags=[False, False],
        prefs={"selectivity_target": "standard"},
        settings=SETTINGS,
        develop_by_idx={},
    )

    # IMG_0000 debe estar seleccionada por supervivencia obligatoria
    res_map = {r["filename"]: r for r in results}
    assert res_map["IMG_0000.jpg"]["label"] in ("selected", "highlighted")
    assert 0 in final_selected
    assert res_map["IMG_0001.jpg"]["label"] == "duplicates"


def test_chapter_pacing_normalizacion():
    """Capítulos con scores bajos no sufren inanición gracias a la normalización por mediana de capítulo."""
    records = [_make_rec(i) for i in range(4)]
    analyses = [_make_analysis(i) for i in range(4)]
    clusters = [
        ImageCluster(0, "portrait", [0, 1], representative_index=0),
        ImageCluster(1, "portrait", [2, 3], representative_index=2),
    ]
    scores = {0: 0.80, 1: 0.70, 2: 0.35, 3: 0.30}
    chapter_map = {0: "dia", 1: "dia", 2: "noche", 3: "noche"}

    results, demoted, final_selected, highlights = apply_decision_logic(
        records=records,
        analyses=analyses,
        clusters=clusters,
        rep_scores=scores,
        trash_flags=[False] * 4,
        prefs={"selectivity_target": "standard"},
        settings=SETTINGS,
        develop_by_idx={},
        chapter_map=chapter_map,
    )

    res_map = {r["filename"]: r for r in results}
    assert res_map["IMG_0000.jpg"]["label"] in ("selected", "highlighted")
    assert res_map["IMG_0002.jpg"]["label"] in ("selected", "highlighted")


def test_trim_excess_to_target():
    """
    Si la selección se pasa de la cuota + 5%, degrada a 1 estrella ('alternative')
    fotos secundarias de ráfaga, protegiendo al ganador, singletons y VIPs.
    """
    records = [_make_rec(i) for i in range(10)]
    analyses = [_make_analysis(i) for i in range(10)]

    clusters = [
        ImageCluster(0, "portrait", [0, 1], representative_index=0),
        ImageCluster(1, "portrait", [2, 3], representative_index=2),
        ImageCluster(2, "portrait", [4], representative_index=4),
        ImageCluster(3, "portrait", [5], representative_index=5),
        ImageCluster(4, "portrait", [6], representative_index=6),
        ImageCluster(5, "portrait", [7], representative_index=7),
        ImageCluster(6, "portrait", [8], representative_index=8),
        ImageCluster(7, "portrait", [9], representative_index=9),
    ]
    records[1].width, records[1].height = 4000, 6000
    records[3].width, records[3].height = 4000, 6000

    scores = {i: 0.90 - i * 0.05 for i in range(10)}
    vip_photos = {4}

    results, demoted, final_selected, highlights = apply_decision_logic(
        records=records,
        analyses=analyses,
        clusters=clusters,
        rep_scores=scores,
        trash_flags=[False] * 10,
        prefs={"selectivity_target": "standard", "target_fraction": 0.20},
        settings=SETTINGS,
        develop_by_idx={},
        vip_photo_indices=vip_photos,
    )

    res_map = {r["filename"]: r for r in results}
    alternatives = [r for r in results if r["label"] == "alternative"]
    assert len(alternatives) > 0
    for alt in alternatives:
        assert alt["stars"] == 1
        assert any("cuota" in reason.lower() for reason in alt["reasons"])

    assert res_map["IMG_0000.jpg"]["label"] in ("selected", "highlighted")
    assert res_map["IMG_0004.jpg"]["label"] in ("selected", "highlighted")
