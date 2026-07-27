"""
taste_model.py — Aprendizaje de gustos del usuario sobre embeddings visuales.
Los ejemplos (duelos + correcciones de Lightroom) se persisten en SQLite
(taste_store) y el scorer es una regresión logística re-entrenada al vuelo.
"""
import logging

import numpy as np
from sklearn.linear_model import BayesianRidge

from services.taste_store import TasteStore
from services.embedding_service import EMBEDDING_DIM, MODEL_VERSION

logger = logging.getLogger(__name__)

# Nº mínimo de ejemplos antes de confiar en el modelo para rankear.
# Por debajo, el ranking usa las heurísticas (fallback frío en main.py).
MIN_EXAMPLES = 50


class TasteModel:
    def __init__(self, store: TasteStore | None = None):
        self.store = store or TasteStore()
        self._clf: BayesianRidge | None = None
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

    def _fit(self) -> BayesianRidge | None:
        if not self._dirty and self._clf is not None:
            return self._clf
        X, y = self.store.load_examples(EMBEDDING_DIM, MODEL_VERSION)
        if len(X) < MIN_EXAMPLES or len(np.unique(y)) < 2:
            return None
        # Usamos Bayes para manejar la incertidumbre.
        # Tolera mejor errores (ruido) en el etiquetado del usuario.
        clf = BayesianRidge(compute_score=True, alpha_1=1e-3, lambda_1=1e-3)
        clf.fit(X, y)
        self._clf = clf
        self._dirty = False
        logger.info(f"Taste model Bayesiano re-entrenado con {len(X)} ejemplos.")
        return clf

    def predict_score(self, embedding: np.ndarray | None) -> float:
        """
        Puntaje de gusto (0..1) para un embedding con factor de contracción.
        Si la incertidumbre es alta, el puntaje se acerca a 0.5 (Neutro).
        """
        if embedding is None or not self.is_trained:
            return 0.5
        clf = self._fit()
        if clf is None:
            return 0.5
        X = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        mean, std = clf.predict(X, return_std=True)
        
        # mean mapea idealmente alrededor de [-1, +1] (nuestras etiquetas)
        # Convertimos a probabilidad cruda usando una sigmoide simple escalada o mapeo lineal
        raw_prob = (mean[0] + 1.0) / 2.0
        raw_prob = max(0.0, min(1.0, raw_prob))
        
        # Shrinkage (Contracción): penaliza predicciones altamente inseguras
        # std suele estar entre 0.1 (muy seguro) y >1.0 (inseguro)
        certainty = float(np.exp(-std[0]))
        
        # Aplica contracción hacia el neutro
        return 0.5 + (raw_prob - 0.5) * certainty


# Instancia global (Singleton)
taste_model = TasteModel()
