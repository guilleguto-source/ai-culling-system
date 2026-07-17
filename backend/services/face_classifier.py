"""
face_classifier.py — Clasificador de atributos faciales aprendido (Fase G3).

Modelo HÍBRIDO: LogisticRegression (con estandarización) sobre el vector
[embedding CLIP del recorte de cara | geometría de MediaPipe]. El embedding
capta apariencia (lentes, contexto); la geometría aporta el detalle fino
(un ojo entrecerrado son unos píxeles) que el embedding del recorte no resuelve.
El StandardScaler evita que las 5 dims de geometría se ahoguen entre las 512
del embedding.

Rol: refina el veredicto de G1 donde ya es más fiable. Se entrena con las
etiquetas de la calibración (G2), sin re-etiquetar nada. Sin datos, manda G1.
"""
import logging

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from services.calibration_store import ATTRIBUTES, CalibrationStore
from services.embedding_service import EMBEDDING_DIM
from services.face_mesh import FEATURE_DIM

logger = logging.getLogger(__name__)


def _make_model() -> "object":
    """Estandariza y clasifica. El scaler va en el pipeline para ajustarse por
    fold en validación cruzada (sin fuga de datos)."""
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced"),
    )

# Mínimo de ejemplos por atributo para confiar en el clasificador. Por debajo,
# manda la geometría de G1: un modelo con 20 ejemplos es ruido con confianza.
MIN_EXAMPLES = 60
# Y al menos esto por clase: 100 ejemplos donde 98 son "abiertos" no enseñan
# a reconocer "cerrados".
MIN_PER_CLASS = 15


class FaceClassifier:
    """Un clasificador por atributo, entrenado bajo demanda."""

    def __init__(self, store: CalibrationStore | None = None):
        self.store = store or CalibrationStore()
        self._clfs: dict[str, LogisticRegression | None] = {}
        self._dirty: set[str] = set(ATTRIBUTES)

    def invalidate(self, attribute: str | None = None) -> None:
        """Marca para re-entrenar (tras nuevas etiquetas)."""
        self._dirty.update(ATTRIBUTES if attribute is None else {attribute})

    def stats(self, attribute: str) -> dict:
        _, y = self.store.training_set(attribute, EMBEDDING_DIM, FEATURE_DIM)
        clases = {v: y.count(v) for v in set(y)}
        return {
            "ejemplos": len(y),
            "por_clase": clases,
            "listo": self._suficiente(y),
        }

    def _suficiente(self, y: list[str]) -> bool:
        if len(y) < MIN_EXAMPLES:
            return False
        clases = {v: y.count(v) for v in set(y)}
        return len(clases) >= 2 and min(clases.values()) >= MIN_PER_CLASS

    def _fit(self, attribute: str):
        if attribute not in self._dirty and attribute in self._clfs:
            return self._clfs[attribute]
        X, y = self.store.training_set(attribute, EMBEDDING_DIM, FEATURE_DIM)
        if not self._suficiente(y):
            self._clfs[attribute] = None
            self._dirty.discard(attribute)
            return None
        clf = _make_model()
        clf.fit(X, y)
        self._clfs[attribute] = clf
        self._dirty.discard(attribute)
        logger.info(f"Clasificador '{attribute}' entrenado con {len(X)} ejemplos.")
        return clf

    def is_ready(self, attribute: str) -> bool:
        return self._fit(attribute) is not None

    def predict(self, attribute: str, vector: np.ndarray | None) -> tuple[str, float]:
        """
        (valor, confianza) a partir del vector híbrido [embedding | geometría].
        Devuelve ("", 0.0) si el clasificador aún no es fiable o falta el vector
        — el llamador debe caer en G1.
        """
        if vector is None:
            return "", 0.0
        clf = self._fit(attribute)
        if clf is None:
            return "", 0.0
        X = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        probs = clf.predict_proba(X)[0]
        i = int(np.argmax(probs))
        return str(clf.classes_[i]), float(probs[i])

    def cross_val_accuracy(self, attribute: str) -> float | None:
        """
        Precisión honesta (validación cruzada): NO se mide sobre los mismos
        ejemplos con los que se entrenó. Sirve para decidir si G3 supera a G1.
        """
        X, y = self.store.training_set(attribute, EMBEDDING_DIM, FEATURE_DIM)
        if not self._suficiente(y):
            return None
        from sklearn.model_selection import cross_val_score
        n = min(5, min({v: y.count(v) for v in set(y)}.values()))
        if n < 2:
            return None
        scores = cross_val_score(_make_model(), X, y, cv=n)
        return float(round(scores.mean(), 3))


# Instancia global (Singleton), como taste_model
face_classifier = FaceClassifier()


# Atributos que refinan los conteos por-cara, en orden de aplicación.
_REFINE_ATTRS = ("subject", "glasses", "eyes", "gaze", "mouth")


def refine_face_counts(analyses) -> int:
    """
    Reemplaza los veredictos por-cara de la geometría (G1) por los del
    clasificador aprendido de tu calibración (G3), atributo por atributo y solo
    donde G3 ya es fiable; en el resto manda G1.

    Se corre en la SELECCIÓN, no en el análisis, para que refleje siempre la
    última calibración sin re-analizar el evento (igual que taste_model).
    Muta `valid_face_count`, `closed_eyes_count`, `looking_away_count`,
    `smiling_count` y `any_closed_eyes`. Devuelve cuántas fotos cambiaron.
    """
    from services import embedding_service, face_mesh
    from services.calibration import face_embedding

    if not embedding_service.is_available():
        return 0
    ready = {at for at in _REFINE_ATTRS if face_classifier.is_ready(at)}
    if not ready:
        return 0

    def verdict(attribute: str, vector, fallback: str) -> str:
        if attribute in ready:
            val, _conf = face_classifier.predict(attribute, vector)
            if val:
                return val
        return fallback

    ajustadas = 0
    for a in analyses:
        if not a.face_attrs or not a.face_bboxes:
            continue
        attrs = [face_mesh.from_dict(d) for d in a.face_attrs]
        valid = closed = away = smiling = 0
        for i, fa in enumerate(attrs):
            if not fa.valid or i >= len(a.face_bboxes):
                continue
            emb = face_embedding(a.path, a.face_bboxes[i])
            # Vector híbrido [embedding | geometría], como en el entrenamiento.
            vec = (np.concatenate([emb, face_mesh.feature_vector(fa)])
                   if emb is not None else None)
            # Caras que el modelo reconoce como no-cara o ilegibles no cuentan.
            if verdict("subject", vec, "persona") != "persona":
                continue
            valid += 1
            # Con lentes oscuros no se ven los ojos ni la mirada: no se penaliza.
            if verdict("glasses", vec, "sin") != "oscuros":
                if verdict("eyes", vec, "cerrados" if fa.eyes_closed else "abiertos") == "cerrados":
                    closed += 1
                if verdict("gaze", vec, "fuera" if fa.looking_away else "camara") == "fuera":
                    away += 1
            if verdict("mouth", vec, "sonrisa" if fa.smiling else "neutra") == "sonrisa":
                smiling += 1

        antes = (a.valid_face_count, a.closed_eyes_count, a.looking_away_count, a.smiling_count)
        if antes != (valid, closed, away, smiling):
            ajustadas += 1
        a.valid_face_count = valid
        a.closed_eyes_count = closed
        a.looking_away_count = away
        a.smiling_count = smiling
        a.any_closed_eyes = closed > 0

    return ajustadas
