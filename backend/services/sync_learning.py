"""
sync_learning.py — Sync incremental: aprender de TODO lo que el fotógrafo hizo
en Lightroom, no solo de las estrellas.

El botón "Sincronizar desde Lightroom" ya alimenta el GUSTO con los cambios de
estrellas (reimport_xmp). Este módulo agrega las otras dos señales: el REVELADO
y el RECORTE que aplicó a las fotos que conservó (keepers), integrándolos al
mismo history_store del bootstrap y re-aprendiendo las recetas por escena.

Así cada evento que sincronizás mejora las tres cosas en una sola pasada, sin
esperar al lote grande del historial.
"""
import logging

from services.history_bootstrap import classify, is_extreme_develop
from services.history_store import HistoryStore

logger = logging.getLogger(__name__)

# Estrellas mínimas para considerar una foto "keeper" cuyo estilo vale aprender.
KEEPER_STARS = 2


def learn_styles_from_event(keepers: list[dict], relearn: bool = True,
                            store: HistoryStore | None = None) -> dict:
    """
    Persiste el revelado/recorte de las keepers de un evento y (por defecto)
    re-aprende las recetas de revelado y recorte por escena.

    keepers: [{path, rating, develop, crop, scene}]. `scene` puede ser "" si
    aún no hay centroides — entonces la foto se guarda pero no entra en las
    recetas por escena hasta el próximo agrupamiento.
    """
    if not keepers:
        return {"guardadas": 0, "escenas_revelado": 0, "escenas_recorte": 0}

    store = store or HistoryStore()
    rows = [{
        "path": k["path"],
        "label": classify(k["rating"], 0),   # 2-3★ → positive
        "rating": k["rating"],
        "pick": 0,
        "capture_time": "",
        "develop": k.get("develop") or {},
        "crop": k.get("crop") or {},
        "develop_extreme": int(is_extreme_develop(k.get("develop") or {})),
        "source": "lightroom-sync",
    } for k in keepers]
    store.upsert(rows)
    store.set_scenes({k["path"]: k["scene"] for k in keepers if k.get("scene")})

    n_dev = n_crop = 0
    if relearn:
        from services.develop_style import learn_recipes
        from services.crop_style import learn_crop_style
        n_dev = len(learn_recipes(store))
        n_crop = len(learn_crop_style(store))

    return {"guardadas": len(rows), "escenas_revelado": n_dev, "escenas_recorte": n_crop}
