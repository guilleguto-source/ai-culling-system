"""
cluster_gates.py — Gates técnicos dentro de un cluster de fotos similares.
Descartan candidatas con defectos técnicos (ojos cerrados, cara borrosa) ANTES
del ranking por gusto. Regla clave: el descarte es RELATIVO al cluster — una
foto solo se elimina si existe otra del mismo grupo sin ese defecto. Si todas
lo tienen, ninguna se descarta (no se pierde el único registro de un momento).
"""
import logging
import statistics

logger = logging.getLogger(__name__)

# Una cara se considera borrosa si su nitidez cae por debajo de este factor
# de la mediana del cluster. Calibrar con fotos reales en la primera prueba.
FACE_SHARPNESS_RELATIVE_FACTOR = 0.5


# Motivos de descarte (claves estables; la UI las traduce).
GATE_OJOS = "ojos_cerrados"
GATE_NITIDEZ = "rostro_blando"


def apply_technical_gates_explained(
    indices: list[int],
    closed_flags: list[bool],
    face_sharpness: list[list[float]],
) -> tuple[list[int], dict[int, str]]:
    """
    Igual que `apply_technical_gates`, pero además devuelve POR QUÉ cayó cada
    descartada. Es la base de la explicabilidad: sin esto la UI no puede decir
    "perdió porque tenía los ojos cerrados" y termina afirmando "mejor score",
    que es falso cuando quien decide es un gate.

    Returns:
        (supervivientes, {índice_descartado: motivo})
    """
    if len(indices) <= 1:
        return list(indices), {}

    survivors = list(indices)
    motivos: dict[int, str] = {}

    # --- Gate 1: ojos cerrados ---
    open_eyes = [i for i in survivors if not _closed(i, closed_flags)]
    if open_eyes and len(open_eyes) < len(survivors):
        dropped = set(survivors) - set(open_eyes)
        logger.debug(f"Gate ojos: descartadas {sorted(dropped)} (hay alternativa con ojos abiertos)")
        for i in dropped:
            motivos[i] = GATE_OJOS
        survivors = open_eyes

    # --- Gate 2: nitidez por rostro (solo entre fotos con caras detectadas) ---
    # Score por imagen = la cara MENOS nítida (en grupos, todos deben salir bien).
    with_faces = [i for i in survivors if _min_sharpness(i, face_sharpness) is not None]
    if len(with_faces) > 1:
        min_sharps = {i: _min_sharpness(i, face_sharpness) for i in with_faces}
        median_sharp = statistics.median(min_sharps.values())
        threshold = median_sharp * FACE_SHARPNESS_RELATIVE_FACTOR
        sharp_enough = [i for i in with_faces if min_sharps[i] >= threshold]
        if sharp_enough and len(sharp_enough) < len(with_faces):
            dropped = set(with_faces) - set(sharp_enough)
            logger.debug(
                f"Gate nitidez: descartadas {sorted(dropped)} "
                f"(umbral {threshold:.1f}, mediana {median_sharp:.1f})"
            )
            for i in dropped:
                motivos[i] = GATE_NITIDEZ
            # Las fotos sin caras no participan de este gate y se conservan.
            survivors = [i for i in survivors if i not in dropped]

    if not survivors:
        return list(indices), {}
    return survivors, motivos


def apply_technical_gates(
    indices: list[int],
    closed_flags: list[bool],
    face_sharpness: list[list[float]],
) -> list[int]:
    """
    Filtra los índices de un cluster aplicando gates técnicos relativos.

    Args:
        indices: Índices de las fotos del cluster (apuntan a las listas globales).
        closed_flags: Por imagen global, True si algún rostro tiene ojos cerrados.
        face_sharpness: Por imagen global, nitidez Laplaciana de cada cara detectada.

    Returns:
        Subconjunto de `indices` que sobrevive los gates. Nunca vacío:
        si todos los candidatos fallan un gate, ese gate no se aplica.
    """
    return apply_technical_gates_explained(indices, closed_flags, face_sharpness)[0]


def _closed(idx: int, closed_flags: list[bool]) -> bool:
    return closed_flags[idx] if idx < len(closed_flags) else False


def _min_sharpness(idx: int, face_sharpness: list[list[float]]) -> float | None:
    sharps = face_sharpness[idx] if idx < len(face_sharpness) else []
    return min(sharps) if sharps else None
