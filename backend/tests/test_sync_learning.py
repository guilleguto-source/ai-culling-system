"""
Test del sync incremental: aprender revelado/recorte de las keepers de un
evento e integrarlas al history_store (además del gusto, que va por separado).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.history_store import HistoryStore
from services.sync_learning import learn_styles_from_event


def test_persiste_keepers_con_estilo(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    keepers = [
        {"path": "a.jpg", "rating": 2, "scene": "0",
         "develop": {"Contrast2012": -10}, "crop": {"CropTop": 0.1, "CropBottom": 0.9,
                                                    "CropLeft": 0.0, "CropRight": 1.0}},
        {"path": "b.jpg", "rating": 3, "scene": "0",
         "develop": {"Contrast2012": -12}, "crop": {}},
    ]
    res = learn_styles_from_event(keepers, relearn=False, store=s)
    assert res["guardadas"] == 2

    # Se guardaron como positivas de fuente lightroom-sync, con su escena
    assert s.counts_by_label() == {"positive": 2}
    assert s.counts_by_scene() == {"0": 2}
    # El revelado quedó consultable para aprender la receta
    devs = list(s.develop_by_scene())
    assert len(devs) == 2 and all(scene == "0" for _p, scene, _d in devs)


def test_extremos_se_marcan(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    keepers = [{"path": "x.jpg", "rating": 2, "scene": "0",
                "develop": {"Exposure2012": 1.4}, "crop": {}}]   # edición extrema
    learn_styles_from_event(keepers, relearn=False, store=s)
    # develop_by_scene excluye extremas → no aporta a la receta
    assert list(s.develop_by_scene()) == []


def test_sin_keepers_no_hace_nada(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    res = learn_styles_from_event([], relearn=True, store=s)
    assert res["guardadas"] == 0 and s.count() == 0
