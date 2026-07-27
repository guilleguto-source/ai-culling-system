"""
cluster_gates.py — Gates técnicos dentro de un cluster de fotos similares.
Descartan candidatas con defectos técnicos (ojos cerrados, cara borrosa, mirada desviada) ANTES
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
GATE_MIRADA = "mirada_desviada"

# Umbrales continuos (MediaPipe FaceLandmarker)
EAR_CLOSED = 0.18
BLINK_CLOSED = 0.5
GAZE_OUT = 0.35
YAW_OUT = 0.5


def _get_worst_face_metrics(face_attrs: list[dict]) -> dict:
    validas = [a for a in face_attrs if a.get("valid")]
    if not validas:
        return {"min_ear": 1.0, "max_blink": 0.0, "mean_smile": 0.0, "max_gaze_out": 0.0, "max_abs_yaw": 0.0}
    return {
        "min_ear": min((a.get("ear", 1.0) for a in validas), default=1.0),
        "max_blink": max((a.get("blink", 0.0) for a in validas), default=0.0),
        "mean_smile": sum(a.get("smile", 0.0) for a in validas) / len(validas) if validas else 0.0,
        "max_gaze_out": max((a.get("gaze_out", 0.0) for a in validas), default=0.0),
        "max_abs_yaw": max((abs(a.get("yaw", 0.0)) for a in validas), default=0.0),
    }


def apply_technical_gates_explained(
    indices: list[int],
    face_attrs_list: list[list[dict]],
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
    metrics = {i: _get_worst_face_metrics(face_attrs_list[i] if i < len(face_attrs_list) else []) for i in indices}

    # --- Gate 1: ojos cerrados ---
    open_eyes = [i for i in survivors if not (metrics[i]["min_ear"] < EAR_CLOSED or metrics[i]["max_blink"] > BLINK_CLOSED)]
    if open_eyes and len(open_eyes) < len(survivors):
        dropped = set(survivors) - set(open_eyes)
        logger.debug(f"Gate ojos: descartadas {sorted(dropped)} (hay alternativa con ojos abiertos)")
        for i in dropped:
            motivos[i] = GATE_OJOS
        survivors = open_eyes

    # --- Gate 2: mirada desviada ---
    looking_camera = [i for i in survivors if not (metrics[i]["max_gaze_out"] > GAZE_OUT or metrics[i]["max_abs_yaw"] > YAW_OUT)]
    if looking_camera and len(looking_camera) < len(survivors):
        dropped = set(survivors) - set(looking_camera)
        logger.debug(f"Gate mirada: descartadas {sorted(dropped)} (hay alternativa mirando a cámara)")
        for i in dropped:
            motivos[i] = GATE_MIRADA
        survivors = looking_camera

    # --- Gate 3: nitidez por rostro (solo entre fotos con caras detectadas) ---
    def _min_sharpness(idx: int) -> float | None:
        sharps = face_sharpness[idx] if idx < len(face_sharpness) else []
        return min(sharps) if sharps else None

    with_faces = [i for i in survivors if _min_sharpness(i) is not None]
    if len(with_faces) > 1:
        min_sharps = {i: _min_sharpness(i) for i in with_faces}
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
            survivors = [i for i in survivors if i not in dropped]

    if not survivors:
        return list(indices), {}
    return survivors, motivos


def apply_technical_gates(
    indices: list[int],
    face_attrs_list: list[list[dict]],
    face_sharpness: list[list[float]],
) -> list[int]:
    """
    Filtra los índices de un cluster aplicando gates técnicos relativos.
    """
    return apply_technical_gates_explained(indices, face_attrs_list, face_sharpness)[0]
