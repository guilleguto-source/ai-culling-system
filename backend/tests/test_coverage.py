"""
Tests de la cobertura por persona (Fase L): agrupamiento a nivel evento y la
política que garantiza al menos una foto seleccionada por identidad.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.face_identity import group_event_identities
from services.decision import photos_for_coverage


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_agrupa_identidades_por_evento():
    ana = _v(1, 0, 0)   # persona A
    beto = _v(0, 1, 0)  # persona B
    embs_by_photo = {
        0: [ana, beto],   # foto 0: A y B
        1: [ana],         # foto 1: solo A
        2: [beto],        # foto 2: solo B
    }
    ids = group_event_identities(embs_by_photo)
    # A y B son dos identidades; foto 0 tiene ambas
    assert len(ids[0]) == 2
    assert ids[1] == ids[1]  # existe
    # la identidad de A en foto1 coincide con una de foto0
    a_id = ids[1][0]
    assert a_id in ids[0]


def test_cobertura_promueve_persona_sin_seleccion():
    # A está en fotos 0,1 ; B solo en foto 2. Seleccionada: {0} (tiene A).
    identities = {0: [0], 1: [0], 2: [1]}   # id 0 = A, id 1 = B
    scores = {0: 0.9, 1: 0.5, 2: 0.7}
    promover = photos_for_coverage(identities, selected={0}, score_by_photo=scores)
    assert promover == {2}   # B no estaba cubierta → se promueve su única foto


def test_cobertura_no_promueve_si_ya_cubierta():
    identities = {0: [0], 1: [0]}   # solo la persona A
    promover = photos_for_coverage(identities, selected={0}, score_by_photo={0: 0.9, 1: 0.5})
    assert promover == set()   # A ya tiene una seleccionada


def test_cobertura_elige_la_de_mayor_score():
    # B (id 1) en fotos 1 y 2, ninguna seleccionada → promueve la de más score
    identities = {0: [0], 1: [1], 2: [1]}
    scores = {0: 0.9, 1: 0.4, 2: 0.8}
    promover = photos_for_coverage(identities, selected={0}, score_by_photo=scores)
    assert promover == {2}
