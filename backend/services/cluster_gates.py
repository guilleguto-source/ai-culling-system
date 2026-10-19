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
GATE_FLASH_MISFIRE = "flash_misfire"
GATE_SONRISA_VIP = "vip_sin_sonrisa"

# Umbrales continuos (MediaPipe FaceLandmarker)
EAR_CLOSED = 0.18
BLINK_CLOSED = 0.5
GAZE_OUT = 0.35
YAW_OUT = 0.5


def compute_vip_weights(
    face_bboxes: list[list[int]],
    face_identities: list[int] | None = None,
    vip_identity_ids: set[int] | None = None,
) -> list[float]:
    """
    Calcula pesos de importancia [0.1 - 4.0] para cada rostro.
    Si se conocen las identidades VIP (ArcFace), los rostros de los protagonistas
    reciben peso VIP absoluto (4.0). De lo contrario, se calcula por área relativa.
    """
    if not face_bboxes:
        return []

    # 1. Prioridad por Identidad ArcFace si está disponible
    if face_identities and vip_identity_ids:
        weights = []
        for ident in face_identities:
            if ident in vip_identity_ids:
                weights.append(4.0)
            else:
                weights.append(0.5)
        return weights

    # 2. Fallback por área relativa
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
        if a.get("valid", True):
            w = vip_weights[i] if vip_weights and i < len(vip_weights) else 1.0
            validas_con_peso.append((a, w))

    if not validas_con_peso:
        return {
            "vip_min_ear": 1.0, "vip_max_blink": 0.0, "vip_max_gaze_out": 0.0, "vip_max_abs_yaw": 0.0,
            "all_min_ear": 1.0, "all_max_blink": 0.0, "all_max_gaze_out": 0.0, "all_max_abs_yaw": 0.0,
            "mean_smile": 0.0, "vip_mean_smile": 0.0, "vip_any_smiling": False,
        }

    # Separar rostros VIP (protagonistas) de secundarios
    max_w = max(w for _, w in validas_con_peso)
    vip_faces = [a for a, w in validas_con_peso if (w >= 3.0 if max_w >= 3.0 else w >= VIP_AREA_THRESHOLD)]
    if not vip_faces:
        vip_faces = [a for a, _ in validas_con_peso]

    all_faces = [a for a, _ in validas_con_peso]

    vip_smiles = [a.get("smile_score", 1.0 if a.get("smile") else 0.0) for a in vip_faces]
    all_smiles = [a.get("smile_score", 1.0 if a.get("smile") else 0.0) for a in all_faces]

    return {
        "vip_min_ear": min((a.get("ear", 1.0) for a in vip_faces), default=1.0),
        "vip_max_blink": max((a.get("blink", 0.0) for a in vip_faces), default=0.0),
        "vip_max_gaze_out": max((a.get("gaze_out", 0.0) for a in vip_faces), default=0.0),
        "vip_max_abs_yaw": max((abs(a.get("yaw", 0.0)) for a in vip_faces), default=0.0),
        "vip_mean_smile": sum(vip_smiles) / len(vip_smiles) if vip_smiles else 0.0,
        "vip_any_smiling": any(a.get("smile", False) or s >= 0.35 for a, s in zip(vip_faces, vip_smiles)),
        "all_min_ear": min((a.get("ear", 1.0) for a in all_faces), default=1.0),
        "all_max_blink": max((a.get("blink", 0.0) for a in all_faces), default=0.0),
        "all_max_gaze_out": max((a.get("gaze_out", 0.0) for a in all_faces), default=0.0),
        "all_max_abs_yaw": max((abs(a.get("yaw", 0.0)) for a in all_faces), default=0.0),
        "mean_smile": sum(all_smiles) / len(all_smiles) if all_smiles else 0.0,
    }


def apply_technical_gates_explained(
    indices: list[int],
    face_attrs_list: list[list[dict]],
    face_sharpness: list[list[float]],
    face_bboxes_list: list[list[list[int]]] | None = None,
    pre_global_lum_list: list[float] | None = None,
    face_identities_list: list[list[int]] | None = None,
    vip_identity_ids: set[int] | None = None,
    vip_smile_relaxed: bool = False,
) -> tuple[list[int], dict[int, str]]:
    """
    Filtra los índices aplicando gates técnicos con discriminación VIP:
    0. Flash Misfire (si se provee luminancia).
    1. Ojos cerrados (prioriza protagonistas).
    2. Mirada desviada (prioriza protagonistas).
    2.5 Sonrisa VIP condicional (se relaja si el VIP casi no sonríe en el evento, ej. niños 2-5 años).
    3. Nitidez por rostro (relativa al cluster, ponderando VIPs).

    Returns:
        (supervivientes, {índice_descartado: motivo})
    """
    if len(indices) <= 1:
        return list(indices), {}

    survivors = list(indices)
    motivos: dict[int, str] = {}

    # --- Gate 0: Flash Misfire ---
    if pre_global_lum_list is not None and len(survivors) >= 2:
        lums = [pre_global_lum_list[i] for i in survivors]
        med_lum = statistics.median(lums)
        if med_lum >= 0.09:
            valid_flash = []
            for i in survivors:
                if pre_global_lum_list[i] < med_lum * 0.4:
                    motivos[i] = GATE_FLASH_MISFIRE
                else:
                    valid_flash.append(i)
            # Solo aplicamos el gate si sobrevive al menos 1
            if valid_flash:
                survivors = valid_flash

    if len(survivors) <= 1:
        return survivors, motivos

    # Calcular pesos VIP por rostro si se proporcionaron bboxes
    vip_weights_by_idx = {}
    if face_bboxes_list:
        for i in indices:
            bboxes = face_bboxes_list[i] if i < len(face_bboxes_list) else []
            identities = face_identities_list[i] if face_identities_list and i < len(face_identities_list) else None
            vip_weights_by_idx[i] = compute_vip_weights(bboxes, identities, vip_identity_ids)

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

    # --- Gate 2.5: Sonrisa del VIP (Condicional a si el VIP suele sonreír) ---
    if not vip_smile_relaxed and len(survivors) > 1:
        vip_smiling = [
            i for i in survivors
            if metrics[i].get("vip_any_smiling", False) or metrics[i].get("vip_mean_smile", 0.0) >= 0.35
        ]
        if vip_smiling and len(vip_smiling) < len(survivors):
            dropped = set(survivors) - set(vip_smiling)
            logger.debug(f"Gate sonrisa VIP: descartadas {sorted(dropped)} (hay alternativa con VIP sonriendo)")
            for i in dropped:
                motivos[i] = GATE_SONRISA_VIP
            survivors = vip_smiling

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
    face_identities_list: list[list[int]] | None = None,
    vip_identity_ids: set[int] | None = None,
    vip_smile_relaxed: bool = False,
) -> list[int]:
    """
    Filtra los índices de un cluster aplicando gates técnicos relativos.
    """
    return apply_technical_gates_explained(
        indices, face_attrs_list, face_sharpness, face_bboxes_list,
        face_identities_list=face_identities_list,
        vip_identity_ids=vip_identity_ids,
        vip_smile_relaxed=vip_smile_relaxed,
    )[0]

