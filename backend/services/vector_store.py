import json
import logging
import hashlib
from pathlib import Path
import numpy as np

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False

from services.embedding_service import EMBEDDING_DIM

logger = logging.getLogger(__name__)

# Directorio donde guardaremos los índices faiss y los mapas de id
VECTOR_STORE_DIR = Path(__file__).parent.parent / "models" / "vector_store"

class VectorStore:
    def __init__(self, directory: str):
        self.directory = directory
        self.dir_hash = hashlib.md5(directory.encode('utf-8')).hexdigest()
        VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
        
        self.index_path = VECTOR_STORE_DIR / f"{self.dir_hash}.faiss"
        self.map_path = VECTOR_STORE_DIR / f"{self.dir_hash}_map.json"
        
        self.index = None
        self.id_to_path = {}
        self.path_to_id = {}
        
        self._load_or_create()

    def _load_or_create(self):
        if not _FAISS_AVAILABLE:
            logger.warning("FAISS no está disponible. Las búsquedas fallarán.")
            return

        if self.index_path.exists() and self.map_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                with open(self.map_path, 'r', encoding='utf-8') as f:
                    # JSON keys son siempre strings, convertimos de vuelta a int
                    str_map = json.load(f)
                    self.id_to_path = {int(k): v for k, v in str_map.items()}
                    self.path_to_id = {v: int(k) for k, v in str_map.items()}
                logger.info(f"Índice FAISS cargado para {self.directory} ({len(self.id_to_path)} vectores)")
            except Exception as e:
                logger.error(f"Error cargando índice FAISS para {self.directory}: {e}")
                self._create_new()
        else:
            self._create_new()

    def _create_new(self):
        if not _FAISS_AVAILABLE:
            return
        
        # Usamos IndexIDMap para permitir añadir IDs arbitrarios (los nuestros)
        # Usamos IndexFlatIP porque nuestros embeddings ya están L2 normalizados,
        # así que Inner Product equivale a Cosine Similarity.
        flat_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self.index = faiss.IndexIDMap(flat_index)
        self.id_to_path = {}
        self.path_to_id = {}
        self.save()

    def save(self):
        if not _FAISS_AVAILABLE or self.index is None:
            return
        try:
            faiss.write_index(self.index, str(self.index_path))
            with open(self.map_path, 'w', encoding='utf-8') as f:
                json.dump(self.id_to_path, f)
        except Exception as e:
            logger.error(f"Error guardando índice FAISS: {e}")

    def add_vectors(self, paths: list[str], vectors: list[np.ndarray]):
        """Añade un lote de vectores al índice."""
        if not _FAISS_AVAILABLE or self.index is None or not vectors:
            return
            
        new_ids = []
        valid_vecs = []
        valid_paths = []
        
        next_id = max(self.id_to_path.keys()) + 1 if self.id_to_path else 0
        
        for path, vec in zip(paths, vectors):
            if path in self.path_to_id:
                # Ya existe, lo saltamos (si quisiéramos actualizar, tendríamos que borrarlo primero)
                continue
                
            self.id_to_path[next_id] = path
            self.path_to_id[path] = next_id
            
            new_ids.append(next_id)
            valid_vecs.append(vec)
            valid_paths.append(path)
            next_id += 1
            
        if valid_vecs:
            vecs_np = np.stack(valid_vecs).astype(np.float32)
            ids_np = np.array(new_ids, dtype=np.int64)
            self.index.add_with_ids(vecs_np, ids_np)
            self.save()

    def search(self, query_vector: np.ndarray, k: int = 50) -> list[dict]:
        """Busca los K vectores más similares."""
        if not _FAISS_AVAILABLE or self.index is None or self.index.ntotal == 0:
            return []
            
        # FAISS espera un array 2D
        q_vec = query_vector.astype(np.float32).reshape(1, -1)
        
        # D = distancias (scores), I = índices
        D, I = self.index.search(q_vec, k)
        
        results = []
        for score, faiss_id in zip(D[0], I[0]):
            if faiss_id != -1 and faiss_id in self.id_to_path:
                results.append({
                    "path": self.id_to_path[faiss_id],
                    "score": float(score)
                })
                
        return results

def get_vector_store(directory: str) -> VectorStore:
    return VectorStore(directory)
