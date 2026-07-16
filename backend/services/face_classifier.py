"""
face_classifier.py — Clasificador de atributos faciales aprendido (Fase G3).

Misma arquitectura que el taste model: LogisticRegression sobre el embedding
CLIP del RECORTE DE CARA (no de la foto entera: una cara pequeña dentro de una
grupal es un detalle que CLIP no captaría al embeber la imagen completa).

Rol: se usa SOLO donde la geometría de MediaPipe (G1) no da la talla. Se
entrena con las etiquetas de la calibración (G2), así que no exige
re-etiquetar nada. Mientras no haya datos suficientes, manda G1.
"""
import logging

import numpy as np
from sklearn.linear_model import LogisticRegression

from services.calibration_store import ATTRIBUTES, CalibrationStore
from services.embedding_service import EMBEDDING_DIM

logger = logging.getLogger(__name__)

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
        X, y = self.store.training_set(attribute, EMBEDDING_DIM)
        clases = {v: y.count(v) for v in set(y)}
        return {
            "ejemplos": len(X),
            "por_clase": clases,
            "listo": self._suficiente(y),
        }

    def _suficiente(self, y: list[str]) -> bool:
        if len(y) < MIN_EXAMPLES:
            return False
        clases = {v: y.count(v) for v in set(y)}
        return len(clases) >= 2 and min(clases.values()) >= MIN_PER_CLASS

    def _fit(self, attribute: str) -> LogisticRegression | None:
        if attribute not in self._dirty and attribute in self._clfs:
            return self._clfs[attribute]
        X, y = self.store.training_set(attribute, EMBEDDING_DIM)
        if not self._suficiente(y):
            self._clfs[attribute] = None
            self._dirty.discard(attribute)
            return None
        clf = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
        clf.fit(X, y)
        self._clfs[attribute] = clf
        self._dirty.discard(attribute)
        logger.info(f"Clasificador '{attribute}' entrenado con {len(X)} ejemplos.")
        return clf

    def is_ready(self, attribute: str) -> bool:
        return self._fit(attribute) is not None

    def predict(self, attribute: str, embedding: np.ndarray | None) -> tuple[str, float]:
        """
        (valor, confianza). Devuelve ("", 0.0) si el clasificador aún no es
        fiable o no hay embedding — el llamador debe caer en G1.
        """
        if embedding is None:
            return "", 0.0
        clf = self._fit(attribute)
        if clf is None:
            return "", 0.0
        X = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        probs = clf.predict_proba(X)[0]
        i = int(np.argmax(probs))
        return str(clf.classes_[i]), float(probs[i])

    def cross_val_accuracy(self, attribute: str) -> float | None:
        """
        Precisión honesta (validación cruzada): NO se mide sobre los mismos
        ejemplos con los que se entrenó. Sirve para decidir si G3 supera a G1.
        """
        X, y = self.store.training_set(attribute, EMBEDDING_DIM)
        if not self._suficiente(y):
            return None
        from sklearn.model_selection import cross_val_score
        n = min(5, min({v: y.count(v) for v in set(y)}.values()))
        if n < 2:
            return None
        scores = cross_val_score(
            LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced"),
            X, y, cv=n)
        return float(round(scores.mean(), 3))


# Instancia global (Singleton), como taste_model
face_classifier = FaceClassifier()
