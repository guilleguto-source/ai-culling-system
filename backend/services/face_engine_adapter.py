"""
face_engine_adapter.py — Patrón Adaptador para motores de detección facial.
Aísla la lógica de negocio (análisis, clustering, escena) de las librerías externas de IA (UniFace, InsightFace, etc.).
"""
import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    """
    Representación agnóstica de una cara detectada.
    """
    bbox: List[int]                     # [x, y, w, h]
    confidence: float                   # 0.0 .. 1.0
    landmarks: List[List[int]] = field(default_factory=list)  # 5 puntos clave [[x, y], ...]
    embedding: Optional[np.ndarray] = None                    # Vector de 512 dims ArcFace
    raw_face: Optional[Any] = None                            # Objeto original de la librería


class FaceEngineAdapter:
    """
    Adaptador unificado para análisis facial.
    """
    def __init__(self, detector: str = "scrfd", det_model: str = "scrfd_500m", conf_threshold: float = 0.5):
        self.detector = detector
        self.det_model = det_model
        self.conf_threshold = conf_threshold
        self._analyzer = None
        self._load_engine()

    def _load_engine(self):
        try:
            # Asegurar directorio de modelos locales
            from pathlib import Path
            base_dir = Path(__file__).resolve().parent.parent
            models_dir = base_dir / "models" / "uniface"
            if models_dir.exists():
                os.environ["UNIFACE_MODELS_DIR"] = str(models_dir)

            from uniface import FaceAnalyzer
            self._analyzer = FaceAnalyzer(
                conf_threshold=self.conf_threshold
            )
            logger.info(f"FaceEngineAdapter inicializado con detector {self.detector}/{self.det_model}")
        except Exception as e:
            logger.error(f"Error cargando motor facial UniFace: {e}")
            self._analyzer = None

    def analyze(self, img_bgr: np.ndarray) -> List[DetectedFace]:
        """
        Analiza una imagen en BGR y retorna una lista estándar de DetectedFace.
        """
        if self._analyzer is None:
            self._load_engine()
            if self._analyzer is None:
                return []

        try:
            raw_faces = self._analyzer.analyze(img_bgr)
            detected: List[DetectedFace] = []
            
            for f in raw_faces:
                # Normalizar bbox a [x, y, w, h]
                bbox = [int(v) for v in getattr(f, "bbox_xywh", [0, 0, 0, 0])]
                conf = float(getattr(f, "confidence", 0.0))
                
                # Landmarks (5 puntos faciales)
                landmarks = []
                raw_lm = getattr(f, "landmarks", None)
                if raw_lm is not None:
                    landmarks = [[int(p[0]), int(p[1])] for p in raw_lm]
                
                # Embedding
                emb = getattr(f, "embedding", None)
                
                detected.append(DetectedFace(
                    bbox=bbox,
                    confidence=conf,
                    landmarks=landmarks,
                    embedding=emb,
                    raw_face=f
                ))
            return detected
        except Exception as e:
            logger.warning(f"Error en analyze con FaceEngineAdapter: {e}")
            return []

    def release(self):
        """Libera la memoria del modelo explícitamente."""
        if self._analyzer is not None:
            del self._analyzer
            self._analyzer = None
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("FaceEngineAdapter memoria liberada.")
