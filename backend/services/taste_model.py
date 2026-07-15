"""
taste_model.py — Aprendizaje de gustos del usuario sobre embeddings visuales.
Los ejemplos (duelos + correcciones de Lightroom) se persisten en SQLite
(taste_store) y el scorer es una regresión logística re-entrenada al vuelo.

Nota: el pickle SGD antiguo (user_taste_model.pkl) queda obsoleto y se ignora
(sus 3 features heurísticas son incompatibles con embeddings de 512 dims).
"""
import logging

import numpy as np
from sklearn.linear_model import LogisticRegression

from services.taste_store import TasteStore
from services.embedding_service import EMBEDDING_DIM, MODEL_VERSION

logger = logging.getLogger(__name__)

# Nº mínimo de ejemplos antes de confiar en el modelo para rankear.
# Por debajo, el ranking usa las heurísticas (fallback frío en main.py).
MIN_EXAMPLES = 50


class TasteModel:
    def __init__(self, store: TasteStore | None = None):
        self.store = store or TasteStore()
        self._clf: LogisticRegression | None = None
        self._dirty = True   # hay ejemplos nuevos sin re-entrenar

    @property
    def n_examples(self) -> int:
        return self.store.count(EMBEDDING_DIM, MODEL_VERSION)

    @property
    def is_trained(self) -> bool:
        """El modelo solo es fiable tras un mínimo de ejemplos compatibles."""
        return self.n_examples >= MIN_EXAMPLES

    def add_example(
        self, embedding: np.ndarray, label: int, source: str, event_dir: str = ""
    ) -> None:
        """Registra un ejemplo (+1 elegida / -1 rechazada) y marca re-entrenamiento."""
        self.store.add_example(
            embedding, label, source, event_dir, model_version=MODEL_VERSION
        )
        self._dirty = True

    def learn_preference(
        self,
        winner_embedding: np.ndarray,
        loser_embedding: np.ndarray,
        source: str = "duel",
        event_dir: str = "",
    ) -> None:
        """Aprende una preferencia A > B: ganadora = +1, perdedora = -1."""
        self.add_example(winner_embedding, +1, source, event_dir)
        self.add_example(loser_embedding, -1, source, event_dir)
        logger.info(f"Preferencia registrada ({self.n_examples} ejemplos, fuente={source}).")

    def _fit(self) -> LogisticRegression | None:
        if not self._dirty and self._clf is not None:
            return self._clf
        X, y = self.store.load_examples(EMBEDDING_DIM, MODEL_VERSION)
        if len(X) < MIN_EXAMPLES or len(np.unique(y)) < 2:
            return None
        clf = LogisticRegression(max_iter=1000, C=1.0)
        clf.fit(X, (y > 0).astype(int))
        self._clf = clf
        self._dirty = False
        logger.info(f"Taste model re-entrenado con {len(X)} ejemplos.")
        return clf

    def predict_score(self, embedding: np.ndarray | None) -> float:
        """
        Puntaje de gusto (0..1) para un embedding. 0.5 neutro si el modelo
        aún no es fiable o no hay embedding disponible.
        """
        if embedding is None or not self.is_trained:
            return 0.5
        clf = self._fit()
        if clf is None:
            return 0.5
        X = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        return float(clf.predict_proba(X)[0][1])


# Instancia global (Singleton)
taste_model = TasteModel()
