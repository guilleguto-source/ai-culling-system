import logging
from services import clip_text_service
from services import embedding_service
from services.vector_store import get_vector_store
from services.analysis_store import get_all_analysis

logger = logging.getLogger(__name__)

def search_photos(query: str, directory: str, limit: int = 50) -> list[dict]:
    """
    Busca fotos que coincidan semánticamente con el texto dado usando FAISS.
    
    Args:
        query: Texto a buscar (ej. "novia de blanco", "perro corriendo").
        directory: Directorio del evento actual.
        limit: Número máximo de resultados a devolver.
        
    Returns:
        Lista de diccionarios con {"path": str, "score": float} ordenados de mayor a menor.
    """
    if not clip_text_service.is_available() or not embedding_service.is_available():
        logger.warning("Búsqueda semántica no disponible: faltan modelos CLIP.")
        return []

    # 1. Obtener embedding del texto
    text_vec = clip_text_service.embed_text(query)
    if text_vec is None:
        return []

    # 2. Cargar índice FAISS del directorio actual
    vs = get_vector_store(directory)
    
    # 3. Construcción lazy del índice FAISS si está vacío o incompleto
    # Verificamos si tenemos fotos analizadas en SQLite para este directorio
    photos = get_all_analysis(directory)
    if photos:
        # Si el índice FAISS tiene menos fotos que las procesadas, sincronizamos
        if vs.index is None or vs.index.ntotal < len(photos):
            paths_to_add = []
            vecs_to_add = []
            
            for p in photos:
                path = p.path
                if path not in vs.path_to_id:
                    vec = embedding_service.load_cached_embedding(path, p.mtime)
                    if vec is not None:
                        paths_to_add.append(path)
                        vecs_to_add.append(vec)

            if paths_to_add:
                logger.info(f"Sincronizando {len(paths_to_add)} vectores en FAISS para {directory}")
                vs.add_vectors(paths_to_add, vecs_to_add)

    # 4. Buscar usando FAISS
    results = vs.search(text_vec, k=limit)
    
    return results
