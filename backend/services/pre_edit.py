"""
pre_edit.py — Estimadores de pre-edición: exposición por rostros y WB con
consenso por sesiones de luz. Todo produce valores crs (Exposure2012,
IncrementalTemperature/Tint) que se escriben en el XMP — reversible.

Reglas (spec 2026-07-15-pre-edicion):
- Exposición: medida en la piel de ESA foto (+bias global), acotada a la
  mediana de su sesión ±0.7 EV.
- WB: las pieles mandan — la mediana de sesión se calcula solo con fotos de
  personas (si hay ≥3); detalles heredan salvo luz genuinamente distinta.
- Sesiones con histéresis: solo ≥4 fotos consecutivas desviadas cortan sesión.
"""
import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# --- Exposición ---
TARGET_SKIN = 0.42     # luminancia lineal objetivo para piel bien expuesta (calibrar en campo)
TARGET_MID = 0.18      # tono medio para fotos sin personas
MAX_EXPOSURE = 1.5     # stops máximos de corrección medida
SESSION_EXPOSURE_BAND = 0.7  # la corrección no se aleja más de esto de la mediana de sesión
EXPOSURE_STEP = 0.05

# --- WB (escala incremental de LR para no-RAW: -100..100) ---
K_TEMP = 100.0         # ganancia (B/R) → unidades incremental
K_TINT = 100.0         # ganancia (R+B)/2G → unidades incremental
MAX_WB = 15.0          # clamp final por foto
MIN_WHITE_FRACTION = 0.005   # % mínimo de pixeles "blancos" para estimar
WHITE_MAX_SAT = 0.25         # saturación máx. de un "blanco": una dominante fuerte lo tiñe
# Referencia de piel: B/R y (R+B)/2G esperados bajo luz neutra
SKIN_BR_REF = 0.62
SKIN_GM_REF = 1.08

# --- Sesiones de luz ---
BREAK_RUN = 4              # fotos consecutivas desviadas para cortar sesión
SESSION_BREAK_DELTA = 12.0 # unidades incremental de desviación sostenida
SESSION_BREAK_EV = 1.0     # o salto de luminancia en EV
MIN_SESSION_VOTES = 5      # sesiones con menos votos heredan de la vecina
MIN_PEOPLE_VOTES = 3       # pieles mandan si la sesión tiene ≥3 votos de piel
DETAIL_OVERRIDE_DELTA = 10.0  # detalle con luz propia: se edita aparte


# ---------------------------------------------------------------- utilidades

def _linear_luminance(img_rgb: np.ndarray) -> np.ndarray:
    """Luminancia lineal aproximada (gamma 2.2) por pixel, 0..1."""
    norm = img_rgb.astype(np.float32) / 255.0
    lum = 0.2126 * norm[..., 0] + 0.7152 * norm[..., 1] + 0.0722 * norm[..., 2]
    return np.power(np.clip(lum, 1e-4, 1.0), 2.2)


def _skin_patches(img_rgb: np.ndarray, face_bboxes: list[list[int]]) -> np.ndarray | None:
    """Pixeles de piel: región central de cada bbox (mejillas/nariz)."""
    h, w = img_rgb.shape[:2]
    patches = []
    for (x, y, fw, fh) in face_bboxes:
        x1 = max(0, x + int(fw * 0.25))
        x2 = min(w, x + int(fw * 0.75))
        y1 = max(0, y + int(fh * 0.40))
        y2 = min(h, y + int(fh * 0.70))
        if x2 > x1 and y2 > y1:
            patches.append(img_rgb[y1:y2, x1:x2].reshape(-1, 3))
    if not patches:
        return None
    return np.concatenate(patches)


# ---------------------------------------------------------------- exposición

def estimate_exposure(img_rgb: np.ndarray, face_bboxes: list[list[int]]) -> float:
    """
    Stops de corrección (sin bias) para exponer bien la foto.
    Con rostros: mediana de luminancia de piel → TARGET_SKIN.
    Sin rostros: mediana global → TARGET_MID.
    """
    if img_rgb is None or img_rgb.size == 0:
        return 0.0
    skin = _skin_patches(img_rgb, face_bboxes) if face_bboxes else None
    if skin is not None and len(skin) > 50:
        lum = _linear_luminance(skin.reshape(1, -1, 3)).ravel()
        target = TARGET_SKIN
    else:
        lum = _linear_luminance(img_rgb).ravel()
        target = TARGET_MID
    measured = float(np.median(lum))
    stops = math.log2(target / max(measured, 1e-4))
    return float(np.clip(stops, -MAX_EXPOSURE, MAX_EXPOSURE))


# ------------------------------------------------------------------------ WB

def estimate_wb(img_rgb: np.ndarray, face_bboxes: list[list[int]]) -> tuple[float, float] | None:
    """
    Estimación de corrección WB (temp_inc, tint_inc) hacia neutro.
    Con personas: prioridad piel. Sin personas: prioridad blancos.
    None si no hay pixeles útiles (la foto no vota; hereda su sesión).
    """
    if img_rgb is None or img_rgb.size == 0:
        return None

    skin = _skin_patches(img_rgb, face_bboxes) if face_bboxes else None
    if skin is not None and len(skin) > 50:
        mean = skin.astype(np.float32).mean(axis=0)
        br_ref, gm_ref = SKIN_BR_REF, SKIN_GM_REF
    else:
        pixels = img_rgb.reshape(-1, 3).astype(np.float32)
        lum = pixels.mean(axis=1)
        mx = pixels.max(axis=1)
        mn = pixels.min(axis=1)
        sat = (mx - mn) / np.maximum(mx, 1e-4)
        thresh = np.percentile(lum, 90)
        mask = (lum >= thresh) & (sat < WHITE_MAX_SAT) & (mx < 250)  # blancos no quemados
        if mask.sum() < len(pixels) * MIN_WHITE_FRACTION:
            return None
        mean = pixels[mask].mean(axis=0)
        br_ref, gm_ref = 1.0, 1.0

    r, g, b = float(mean[0]), float(mean[1]), float(mean[2])
    if min(r, g, b) < 1.0:
        return None
    # Dominante cálida → B/R bajo → temp negativa (enfriar). LR: + = más cálido.
    temp = K_TEMP * ((b / r) - br_ref)
    # Dominante verde → (R+B)/2G bajo → tint positiva (magenta). LR: + = magenta.
    tint = K_TINT * (gm_ref - (r + b) / (2.0 * g))
    return (float(np.clip(temp, -30, 30)), float(np.clip(tint, -30, 30)))


# ------------------------------------------------------------ sesiones de luz

@dataclass
class PhotoSignature:
    """Firma de luz de una foto (en orden temporal)."""
    index: int                 # índice en la lista global de records
    has_people: bool
    wb: tuple[float, float] | None   # estimación propia (None = no vota)
    lum_ev: float                    # log2(luminancia mediana / 0.18)


@dataclass
class LightSession:
    indices: list[int] = field(default_factory=list)      # posiciones en la lista de firmas
    wb: tuple[float, float] = (0.0, 0.0)                  # mediana aplicable
    exposure_median: float = 0.0


def _median_wb(votes: list[tuple[float, float]]) -> tuple[float, float]:
    temps = sorted(v[0] for v in votes)
    tints = sorted(v[1] for v in votes)
    return (temps[len(temps) // 2], tints[len(tints) // 2])


def _deviates(sig: PhotoSignature, med_wb: tuple[float, float], med_ev: float) -> bool:
    if abs(sig.lum_ev - med_ev) > SESSION_BREAK_EV:
        return True
    if sig.wb is None:
        return False
    return (abs(sig.wb[0] - med_wb[0]) > SESSION_BREAK_DELTA
            or abs(sig.wb[1] - med_wb[1]) > SESSION_BREAK_DELTA)


def segment_light_sessions(signatures: list[PhotoSignature]) -> list[list[int]]:
    """
    Corta la línea de tiempo en sesiones de luz con histéresis: una sesión
    solo se rompe con ≥BREAK_RUN fotos consecutivas desviadas. Detalles o
    close-ups sueltos en medio NO rompen la continuidad.
    Retorna listas de posiciones (índices dentro de `signatures`).
    """
    if not signatures:
        return []

    sessions: list[list[int]] = [[0]]
    run: list[int] = []   # posiciones consecutivas desviadas (candidatas a nueva sesión)

    def session_medians(positions: list[int]) -> tuple[tuple[float, float], float]:
        votes = [signatures[p].wb for p in positions if signatures[p].wb is not None]
        med_wb = _median_wb(votes) if votes else (0.0, 0.0)
        evs = sorted(signatures[p].lum_ev for p in positions)
        return med_wb, evs[len(evs) // 2]

    for pos in range(1, len(signatures)):
        current = sessions[-1]
        med_wb, med_ev = session_medians(current + run)
        base_wb, base_ev = session_medians(current)
        if _deviates(signatures[pos], base_wb, base_ev):
            run.append(pos)
            if len(run) >= BREAK_RUN:
                sessions.append(run)      # cambio sostenido: nueva sesión
                run = []
        else:
            current.extend(run)           # fue un paréntesis (detalle/close-up)
            run = []
            current.append(pos)

    if run:
        # Cola desviada corta: se queda en la última sesión
        sessions[-1].extend(run)
    return sessions


def compute_pre_edits(
    signatures: list[PhotoSignature],
    exposure_stops: list[float],
    bias: float,
    preset_wb_bias: tuple[float, float] = (0.0, 0.0),
) -> dict[int, dict]:
    """
    Calcula los ajustes finales por foto (keyed por PhotoSignature.index).
    `signatures` y `exposure_stops` van en el mismo orden temporal.

    WB: mediana de sesión (pieles mandan) + sesgo del preset, clamp ±MAX_WB.
    Exposición: propia, acotada a mediana de sesión ±SESSION_EXPOSURE_BAND,
    + bias, redondeada a EXPOSURE_STEP.
    """
    sessions = segment_light_sessions(signatures)
    results: dict[int, dict] = {}

    # WB por sesión: solo votan pieles si hay suficientes
    session_wbs: list[tuple[float, float] | None] = []
    for positions in sessions:
        people = [signatures[p].wb for p in positions
                  if signatures[p].has_people and signatures[p].wb is not None]
        allv = [signatures[p].wb for p in positions if signatures[p].wb is not None]
        votes = people if len(people) >= MIN_PEOPLE_VOTES else allv
        if len(votes) >= MIN_SESSION_VOTES:
            session_wbs.append(_median_wb(votes))
        else:
            session_wbs.append(None)   # hereda después

    # Herencia para sesiones chicas: la vecina con WB más cercana en el tiempo
    for i, wb in enumerate(session_wbs):
        if wb is not None:
            continue
        neighbors = [j for j in range(len(sessions)) if session_wbs[j] is not None]
        if neighbors:
            j = min(neighbors, key=lambda j: abs(j - i))
            session_wbs[i] = session_wbs[j]
        else:
            # Ningún consenso en todo el evento: usar votos propios o neutro
            votes = [signatures[p].wb for p in sessions[i] if signatures[p].wb is not None]
            session_wbs[i] = _median_wb(votes) if votes else (0.0, 0.0)

    for s_idx, positions in enumerate(sessions):
        wb_t, wb_i = session_wbs[s_idx]
        exp_med = sorted(exposure_stops[p] for p in positions)[len(positions) // 2]

        for p in positions:
            sig = signatures[p]
            # WB: detalle con luz genuinamente distinta se edita aparte
            t, i = wb_t, wb_i
            if not sig.has_people and sig.wb is not None:
                if (abs(sig.wb[0] - wb_t) > DETAIL_OVERRIDE_DELTA
                        or abs(sig.wb[1] - wb_i) > DETAIL_OVERRIDE_DELTA):
                    t, i = sig.wb
            t = float(np.clip(t + preset_wb_bias[0], -MAX_WB, MAX_WB))
            i = float(np.clip(i + preset_wb_bias[1], -MAX_WB, MAX_WB))

            # Exposición: propia acotada a la sesión, + bias
            e = float(np.clip(exposure_stops[p],
                              exp_med - SESSION_EXPOSURE_BAND,
                              exp_med + SESSION_EXPOSURE_BAND))
            e = round((e + bias) / EXPOSURE_STEP) * EXPOSURE_STEP

            results[sig.index] = {
                "Exposure2012": round(e, 2),
                "IncrementalTemperature": round(t, 1),
                "IncrementalTint": round(i, 1),
            }

    logger.info(f"Pre-edición: {len(sessions)} sesiones de luz, {len(results)} fotos.")
    return results
