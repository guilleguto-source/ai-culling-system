"""
cluster_gates.py — Gates técnicos dentro de un cluster de fotos similares.
Descartan candidatas con defectos técnicos (ojos cerrados, cara borrosa, mirada desviada) ANTES
del ranking por gusto. Regla clave: el descarte es RELATIVO al cluster — una
foto solo se elimina si existe otra del mismo grupo sin ese defecto. Si todas
lo tienen, ninguna se descarta (no se pierde el único registro de un momento).

PONDERACIÓN VIP:
En fotos de grupo/pareja, el protagonista (rostro más grande y central) tiene
prioridad máxima. El parpadeo de una persona secundaria al fondo no descarta
la toma si los protagonistas están perfectos.
"""
import logging
import statistics

logger = logging.getLogger(__name__)

# Una cara se considera borrosa si su nitidez cae por debajo de este factor
# de la mediana del cluster. Calibrar con fotos reales en la primera prueba.
FACE_SHARPNESS_RELATIVE_FACTOR = 0.5

# Umbral de área relativa para clasificar un rostro como VIP/protagonista
VIP_AREA_THRESHOLD = 0.35

# Motivos de descarte (claves estables; la UI las traduce).
GATE_OJOS = "ojos_cerrados"
GATE_NITIDEZ = "rostro_blando"
GATE_MIRADA = "mirada_desviada"

# Umbrales continuos (MediaPipe FaceLandmarker)
EAR_CLOSED = 0.18
BLINK_CLOSED = 0.5
GAZE_OUT = 0.35
YAW_OUT = 0.5


def compute_vip_weights(face_bboxes: list[list[int]]) -> list[float]:
    """
    Calcula pesos de importancia [0.1 - 1.0] para cada rostro según su área (w*h).
    Rostros con área >= 35% del rostro mayor obtienen peso VIP alto (1.0).
    Rostros pequeños en el fondo obtienen peso proporcionalmente reducido.
    """
    if not face_bboxes:
        return []
    areas = [max(1, int(b[2] * b[3])) if len(b) >= 4 else 1 for b in face_bboxes]
    max_area = max(areas)
    if max_area <= 0:
        return [1.0] * len(face_bboxes)

    weights = []
    for a in areas:
        rel = a / max_area
        if rel >= VIP_AREA_THRESHOLD:
            weights.append(1.0)
        else:
            weights.append(float(round(max(0.1, rel), 3)))
    return weights


def _get_face_metrics_with_vip(
    face_attrs: list[dict],
    vip_weights: list[float] | None = None,
) -> dict:
    validas_con_peso = []
    for i, a in enumerate(face_attrs):
        if a.get("valid"):
            w = vip_weights[i] if vip_weights and i < len(vip_weights) else 1.0
            validas_con_peso.append((a, w))

    if not validas_con_peso:
        return {
            "vip_min_ear": 1.0, "vip_max_blink": 0.0, "vip_max_gaze_out": 0.0, "vip_max_abs_yaw": 0.0,
            "all_min_ear": 1.0, "all_max_blink": 0.0, "all_max_gaze_out": 0.0, "all_max_abs_yaw": 0.0,
            "mean_smile": 0.0,
        }

    # Separar rostros VIP (protagonistas) de secundarios
    vip_faces = [a for a, w in validas_con_peso if w >= VIP_AREA_THRESHOLD]
    if not vip_faces:
        vip_faces = [a for a, _ in validas_con_peso]

    all_faces = [a for a, _ in validas_con_peso]

    return {
        "vip_min_ear": min((a.get("ear", 1.0) for a in vip_faces), default=1.0),
        "vip_max_blink": max((a.get("blink", 0.0) for a in vip_faces), default=0.0),
        "vip_max_gaze_out": max((a.get("gaze_out", 0.0) for a in vip_faces), default=0.0),
        "vip_max_abs_yaw": max((abs(a.get("yaw", 0.0)) for a in vip_faces), default=0.0),
        "all_min_ear": min((a.get("ear", 1.0) for a in all_faces), default=1.0),
        "all_max_blink": max((a.get("blink", 0.0) for a in all_faces), default=0.0),
        "all_max_gaze_out": max((a.get("gaze_out", 0.0) for a in all_faces), default=0.0),
        "all_max_abs_yaw": max((abs(a.get("yaw", 0.0)) for a in all_faces), default=0.0),
        "mean_smile": sum(a.get("smile", 0.0) for a in all_faces) / len(all_faces) if all_faces else 0.0,
    }


def apply_technical_gates_explained(
    indices: list[int],
    face_attrs_list: list[list[dict]],
    face_sharpness: list[list[float]],
    face_bboxes_list: list[list[list[int]]] | None = None,
) -> tuple[list[int], dict[int, str]]:
    """
    Filtra los índices aplicando gates técnicos con discriminación VIP:
    1. Ojos cerrados (prioriza protagonistas).
    2. Mirada desviada (prioriza protagonistas).
    3. Nitidez por rostro (relativa al cluster).

    Returns:
        (supervivientes, {índice_descartado: motivo})
    """
    if len(indices) <= 1:
        return list(indices), {}

    survivors = list(indices)
    motivos: dict[int, str] = {}

    # Calcular pesos VIP por rostro si se proporcionaron bboxes
    vip_weights_by_idx = {}
    if face_bboxes_list:
        for i in indices:
            bboxes = face_bboxes_list[i] if i < len(face_bboxes_list) else []
            vip_weights_by_idx[i] = compute_vip_weights(bboxes)

    metrics = {
        i: _get_face_metrics_with_vip(
            face_attrs_list[i] if i < len(face_attrs_list) else [],
            vip_weights_by_idx.get(i),
        )
        for i in indices
    }

    # --- Gate 1: ojos cerrados ---
    # Paso 1.1: Filtrar primero por caras VIP (protagonistas)
    vip_open_eyes = [
        i for i in survivors
        if not (metrics[i]["vip_min_ear"] < EAR_CLOSED or metrics[i]["vip_max_blink"] > BLINK_CLOSED)
    ]
    if vip_open_eyes and len(vip_open_eyes) < len(survivors):
        dropped = set(survivors) - set(vip_open_eyes)
        logger.debug(f"Gate ojos VIP: descartadas {sorted(dropped)} (hay alternativa con protagonistas con ojos abiertos)")
        for i in dropped:
            motivos[i] = GATE_OJOS
        survivors = vip_open_eyes

    # Paso 1.2: Si hay empate entre varias fotos con VIPs abiertos, desempatar si alguna tiene TODAS las caras abiertas
    if len(survivors) > 1:
        all_open_eyes = [
            i for i in survivors
            if not (metrics[i]["all_min_ear"] < EAR_CLOSED or metrics[i]["all_max_blink"] > BLINK_CLOSED)
        ]
        if all_open_eyes and len(all_open_eyes) < len(survivors):
            dropped = set(survivors) - set(all_open_eyes)
            logger.debug(f"Gate ojos secundarios: descartadas {sorted(dropped)} (hay alternativa con todos los ojos abiertos)")
            for i in dropped:
                motivos[i] = GATE_OJOS
            survivors = all_open_eyes

    # --- Gate 2: mirada desviada ---
    # Paso 2.1: Filtrar caras VIP
    vip_looking = [
        i for i in survivors
        if not (metrics[i]["vip_max_gaze_out"] > GAZE_OUT or metrics[i]["vip_max_abs_yaw"] > YAW_OUT)
    ]
    if vip_looking and len(vip_looking) < len(survivors):
        dropped = set(survivors) - set(vip_looking)
        logger.debug(f"Gate mirada VIP: descartadas {sorted(dropped)} (hay alternativa con protagonistas mirando a cámara)")
        for i in dropped:
            motivos[i] = GATE_MIRADA
        survivors = vip_looking

    # Paso 2.2: Desempate secundario en mirada
    if len(survivors) > 1:
        all_looking = [
            i for i in survivors
            if not (metrics[i]["all_max_gaze_out"] > GAZE_OUT or metrics[i]["all_max_abs_yaw"] > YAW_OUT)
        ]
        if all_looking and len(all_looking) < len(survivors):
            dropped = set(survivors) - set(all_looking)
            logger.debug(f"Gate mirada secundaria: descartadas {sorted(dropped)}")
            for i in dropped:
                motivos[i] = GATE_MIRADA
            survivors = all_looking

    # --- Gate 3: nitidez por rostro (solo entre fotos con caras detectadas) ---
    def _min_sharpness(idx: int) -> float | None:
        sharps = face_sharpness[idx] if idx < len(face_sharpness) else []
        if not sharps:
            return None
        # Si tenemos pesos VIP, evaluar la nitidez del conjunto de caras VIP
        weights = vip_weights_by_idx.get(idx, [])
        if weights and len(weights) == len(sharps):
            vip_sharps = [s for s, w in zip(sharps, weights) if w >= VIP_AREA_THRESHOLD]
            if vip_sharps:
                return min(vip_sharps)
        return min(sharps)

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
    face_bboxes_list: list[list[list[int]]] | None = None,
) -> list[int]:
    """
    Filtra los índices de un cluster aplicando gates técnicos relativos.
    """
    return apply_technical_gates_explained(indices, face_attrs_list, face_sharpness, face_bboxes_list)[0]

