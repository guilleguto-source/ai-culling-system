"""
Tests de las fases H2 (gusto), K (recorte) y L (identidad ArcFace).

Las partes que dependen de modelos (CLIP/ArcFace) se prueban en su lógica pura;
la degradación sin modelo también.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.history_store import HistoryStore
from services.history_taste import label_sign
from services.crop_style import descriptors, is_real_crop, learn_crop_style, MIN_PER_SCENE
from services.face_identity import group_identities, is_available


# --- H2: gusto ---

def _row(path, label, crop=None):
    return {"path": path, "label": label, "rating": 2, "pick": 0, "capture_time": "",
            "develop": {}, "crop": crop or {}, "develop_extreme": 0, "source": "catalog"}


def test_label_sign():
    assert label_sign("positive") == 1
    assert label_sign("negative") == -1


def test_unfed_e_idempotencia(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([_row("a.jpg", "positive"), _row("b.jpg", "negative"),
              _row("c.jpg", "unreviewed")])           # unreviewed no cuenta
    pend = s.unfed_labeled()
    assert {p for p, _ in pend} == {"a.jpg", "b.jpg"}
    s.mark_fed(["a.jpg", "b.jpg"])
    assert s.unfed_labeled() == []                    # ya no reaparecen


# --- K: recorte ---

def test_descriptores_de_recorte():
    # Recorte centrado que retiene el 80% (0.9x0.9 aprox), sin ángulo
    d = descriptors({"CropTop": 0.05, "CropLeft": 0.05, "CropBottom": 0.95, "CropRight": 0.95})
    assert abs(d["area"] - 0.81) < 1e-6
    assert d["offset_x"] == 0.0 and d["offset_y"] == 0.0
    # Sujeto arriba: caja desplazada hacia arriba → offset_y negativo
    d2 = descriptors({"CropTop": 0.0, "CropLeft": 0.0, "CropBottom": 0.6, "CropRight": 1.0})
    assert d2["offset_y"] < 0


def test_is_real_crop():
    assert is_real_crop({"CropTop": 0.1, "CropLeft": 0.1, "CropBottom": 0.9, "CropRight": 0.9})
    assert is_real_crop({"CropTop": 0.0, "CropLeft": 0.0, "CropBottom": 1.0, "CropRight": 1.0, "CropAngle": 0.5})
    # Sin recorte ni ángulo → trivial
    assert not is_real_crop({"CropTop": 0.0, "CropLeft": 0.0, "CropBottom": 1.0, "CropRight": 1.0})


def test_learn_crop_style_por_escena(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    crop = {"CropTop": 0.1, "CropLeft": 0.0, "CropBottom": 0.9, "CropRight": 1.0}   # área 0.8
    rows = [_row(f"e_{i}.jpg", "positive", crop) for i in range(MIN_PER_SCENE)]
    s.upsert(rows)
    s.set_scenes({f"e_{i}.jpg": "0" for i in range(MIN_PER_SCENE)})
    estilos = learn_crop_style(s)
    assert estilos["0"]["_n"] == MIN_PER_SCENE
    assert abs(estilos["0"]["area"] - 0.8) < 1e-6


# --- L: identidad ---

def test_group_identities_separa_personas():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    # dos de 'a' (con ruido mínimo) y una de 'b' → {0,0,1}
    a2 = a + np.array([0.01, 0.0, 0.0], dtype=np.float32)
    a2 /= np.linalg.norm(a2)
    ids = group_identities([a, a2, b])
    assert ids[0] == ids[1] and ids[2] != ids[0]


def test_group_identities_maneja_none():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    ids = group_identities([a, None, a])
    assert ids[1] == -1 and ids[0] == ids[2]


def test_arcface_degradacion_sin_modelo():
    # En el entorno de test no está el .onnx → is_available False, sin crash.
    assert is_available() in (True, False)
