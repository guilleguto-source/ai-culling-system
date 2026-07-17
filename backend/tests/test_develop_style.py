"""
Tests de la Fase J: estilo de revelado por escena.

La receta es la mediana de los campos de "look" sobre positivas no-extremas,
por escena, y solo si hay suficientes ejemplos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.history_store import HistoryStore
from services.develop_style import learn_recipes, style_for_scene, MIN_PER_SCENE


def _row(path, scene, label, develop, extreme=0):
    return {"path": path, "label": label, "rating": 2, "pick": 0,
            "capture_time": "", "develop": develop, "crop": {},
            "develop_extreme": extreme, "source": "catalog"}


def _poblar_escena(store, scene, n, contrast, label="positive", extreme=0, tag=""):
    # `tag` evita colisión de rutas cuando se puebla la misma escena varias veces.
    paths = [f"{scene}_{tag}{label}_{i}.jpg" for i in range(n)]
    store.upsert([
        _row(p, scene, label, {"Contrast2012": contrast, "Vibrance": 10}, extreme)
        for p in paths
    ])
    store.set_scenes({p: scene for p in paths})


def test_receta_es_la_mediana_por_escena(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    _poblar_escena(s, "0", MIN_PER_SCENE, contrast=-15)
    _poblar_escena(s, "1", MIN_PER_SCENE, contrast=25)
    recipes = learn_recipes(s)
    assert recipes["0"]["Contrast2012"] == -15
    assert recipes["1"]["Contrast2012"] == 25
    assert recipes["0"]["_n"] == MIN_PER_SCENE


def test_escena_con_pocos_ejemplos_no_tiene_receta(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    _poblar_escena(s, "0", MIN_PER_SCENE - 1, contrast=-15)   # una menos del mínimo
    assert "0" not in learn_recipes(s)


def test_excluye_negativas_y_extremas(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    _poblar_escena(s, "0", MIN_PER_SCENE, contrast=-15, tag="ok")           # positivas normales
    _poblar_escena(s, "0", 50, contrast=90, label="negative", tag="neg")   # rechazadas: no cuentan
    _poblar_escena(s, "0", 50, contrast=90, extreme=1, tag="ext")          # extremas: no cuentan
    recipes = learn_recipes(s)
    assert recipes["0"]["Contrast2012"] == -15   # no lo arrastran las de 90


def test_style_for_scene_omite_metadato(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    _poblar_escena(s, "0", MIN_PER_SCENE, contrast=-15)
    recipes = learn_recipes(s)
    estilo = style_for_scene("0", recipes)
    assert "_n" not in estilo and estilo["Contrast2012"] == -15
    assert style_for_scene(None, recipes) == {}
    assert style_for_scene("99", recipes) == {}   # escena sin receta
