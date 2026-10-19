"""
face_identity.py — Agrupación de identidades por embeddings UniFace (ArcFace).

Los embeddings ya NO se calculan aquí: vienen directamente de FaceAnalyzer
(uniface) vía scene_classifier → analysis.face_identities.

Este módulo conserva únicamente la lógica de AGRUPACIÓN (clustering coseno)
para la fase de cobertura por persona en culling.py.
"""
import numpy as np

IDENTITY_THRESHOLD = 0.38  # distancia coseno máx. para "misma persona"


def group_identities(embeddings: list[np.ndarray],
                     threshold: float = IDENTITY_THRESHOLD) -> list[int]:
    """
    Agrupa embeddings de rostro por identidad (greedy por coseno). Devuelve una
    etiqueta de identidad por embedding (mismo índice de entrada). Lógica pura.
    `None` en la entrada → identidad -1.
    """
    ids: list[int] = []
    centroides: list[np.ndarray] = []
    for emb in embeddings:
        if emb is None:
            ids.append(-1)
            continue
        v = np.asarray(emb, dtype=np.float32)
        mejor, mejor_d = -1, threshold
        for k, c in enumerate(centroides):
            d = 1.0 - float(np.dot(v, c))
            if d < mejor_d:
                mejor, mejor_d = k, d
        if mejor >= 0:
            ids.append(mejor)
        else:
            ids.append(len(centroides))
            centroides.append(v)
    return ids


def group_event_identities(embs_by_photo: dict,
                           threshold: float = IDENTITY_THRESHOLD) -> dict:
    """
    Agrupa TODOS los rostros de un evento por identidad y mapea de vuelta a cada
    foto. Entrada: {idx_foto: [embedding por rostro]}. Salida:
    {idx_foto: [ids de identidad presentes]}. Fotos sin rostro no aparecen.
    """
    flat, owners = [], []
    for idx, embs in embs_by_photo.items():
        for e in embs:
            if e is not None:
                flat.append(e)
                owners.append(idx)
    ids = group_identities(flat, threshold)
    out: dict = {}
    for owner, ident in zip(owners, ids):
        if ident >= 0:
            out.setdefault(owner, set()).add(ident)
    return {k: sorted(v) for k, v in out.items()}


def rank_vip_identities(identidades: dict, top_n: int = 3) -> set[int]:
    """
    Identifica los protagonistas del evento por frecuencia de aparición.

    Entrada: {idx_foto: [id_identidad, ...]}  (salida de group_event_identities)
    Salida:  set con los top_n ids de identidad más frecuentes.

    Los protagonistas (novios, quinceañera, homenajeado) aparecen en la
    gran mayoría de las fotos del evento y serán bonificados durante el scoring.
    """
    from collections import Counter
    counter: Counter = Counter()
    for ids_en_foto in identidades.values():
        for ident_id in ids_en_foto:
            if ident_id >= 0:
                counter[ident_id] += 1
    if not counter:
        return set()
    top = counter.most_common(top_n)
    return {ident_id for ident_id, _ in top}
