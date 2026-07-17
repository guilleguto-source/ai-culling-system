"""Tests de la calibración: almacén, acuerdo con el detector e incertidumbre."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.calibration_store import CalibrationStore, ATTRIBUTES
from services import face_mesh
from services.face_mesh import FaceAttributes


def _store(tmp_path):
    return CalibrationStore(db_path=tmp_path / "cal.db")


# --- Almacén ---

def test_guarda_y_cuenta(tmp_path):
    s = _store(tmp_path)
    s.add_label("a.jpg", 0, "eyes", "abiertos", predicted="cerrados")
    s.add_label("a.jpg", 0, "gaze", "fuera", predicted="fuera")
    assert s.count() == 2
    assert s.count("eyes") == 1


def test_re_etiquetar_reemplaza(tmp_path):
    s = _store(tmp_path)
    s.add_label("a.jpg", 0, "eyes", "abiertos")
    s.add_label("a.jpg", 0, "eyes", "cerrados")
    assert s.count("eyes") == 1          # no duplica: corrige


def test_valor_invalido_falla(tmp_path):
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.add_label("a.jpg", 0, "eyes", "guiñando")
    with pytest.raises(ValueError):
        s.add_label("a.jpg", 0, "pelo", "rizado")


def test_caras_ya_etiquetadas(tmp_path):
    s = _store(tmp_path)
    s.add_label("a.jpg", 0, "eyes", "abiertos")
    s.add_label("b.jpg", 2, "gaze", "camara")
    assert s.labeled_faces() == {("a.jpg", 0), ("b.jpg", 2)}


# --- Medición del detector (el objetivo principal de G2) ---

def test_acuerdo_mide_la_precision_real(tmp_path):
    s = _store(tmp_path)
    # el detector acierta 3 de 4
    for i, (real, pred) in enumerate([("abiertos", "abiertos"), ("abiertos", "abiertos"),
                                      ("cerrados", "cerrados"), ("abiertos", "cerrados")]):
        s.add_label(f"f{i}.jpg", 0, "eyes", real, predicted=pred)
    a = s.agreement("eyes")
    assert a == {"total": 4, "aciertos": 3, "precision": 0.75}


def test_acuerdo_sin_datos(tmp_path):
    assert _store(tmp_path).agreement("eyes")["precision"] is None


def test_acuerdo_ignora_sin_prediccion(tmp_path):
    s = _store(tmp_path)
    s.add_label("a.jpg", 0, "eyes", "abiertos", predicted="")
    assert s.agreement("eyes")["total"] == 0


# --- Set de entrenamiento híbrido para G3 ---

def test_training_set_requiere_embedding_y_features(tmp_path):
    s = _store(tmp_path)
    emb, feat = np.ones(512, dtype=np.float32), np.ones(5, dtype=np.float32)
    s.add_label("a.jpg", 0, "eyes", "abiertos", embedding=emb, features=feat)
    s.add_label("b.jpg", 0, "eyes", "cerrados", embedding=emb)   # sin features
    s.add_label("c.jpg", 0, "eyes", "cerrados", features=feat)   # sin embedding
    X, y = s.training_set("eyes", 512, 5)
    # Solo la fila con ambos entra; el vector es [embedding | features].
    assert X.shape == (1, 517) and y == ["abiertos"]


def test_training_set_descarta_dim_incompatible(tmp_path):
    s = _store(tmp_path)
    s.add_label("a.jpg", 0, "eyes", "abiertos",
                embedding=np.ones(64, dtype=np.float32), features=np.ones(5, dtype=np.float32))
    X, y = s.training_set("eyes", 512, 5)
    assert len(X) == 0


# --- Muestreo por incertidumbre ---

def test_incertidumbre_alta_en_el_filo_del_umbral():
    filo = FaceAttributes(valid=True, ear=face_mesh.EAR_CLOSED, blink=0.2)
    claro = FaceAttributes(valid=True, ear=0.45, blink=0.01)
    assert face_mesh.uncertainty(filo, "eyes") > face_mesh.uncertainty(claro, "eyes")


def test_incertidumbre_alta_si_las_señales_se_contradicen():
    """EAR dice abierto pero el blendshape dice parpadeo: hay que preguntar."""
    contradice = FaceAttributes(valid=True, ear=0.40, blink=0.9)
    concuerda = FaceAttributes(valid=True, ear=0.40, blink=0.02)
    assert face_mesh.uncertainty(contradice, "eyes") > face_mesh.uncertainty(concuerda, "eyes")


def test_cara_invalida_no_se_pregunta():
    assert face_mesh.uncertainty(FaceAttributes(valid=False), "eyes") == 0.0


def test_prediccion_se_pre_marca():
    a = FaceAttributes(valid=True, ear=0.30, blink=0.05, gaze_out=0.1, smile=0.7)
    assert face_mesh.predict(a, "eyes") == "abiertos"
    assert face_mesh.predict(a, "gaze") == "camara"
    assert face_mesh.predict(a, "mouth") == "sonrisa"
    assert face_mesh.predict(FaceAttributes(valid=False), "eyes") == ""


def test_predicciones_son_valores_validos():
    """La predicción pre-marcada debe existir en el vocabulario del atributo.
    "" = sin predicción (atributo sin señal geométrica, p.ej. glasses): la UI
    no pre-marca nada y `agreement` lo excluye."""
    a = FaceAttributes(valid=True, ear=0.1, blink=0.9, gaze_out=0.9, smile=0.9)
    for at in ATTRIBUTES:
        assert face_mesh.predict(a, at) in ATTRIBUTES[at] + [""]
