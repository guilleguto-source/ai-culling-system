import cv2
from typing import Any
from pathlib import Path
from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.auto_crop import LEVEL_LIMITS, propose_crop, detect_horizon_angle

def _bad_faces(a: PhotoAnalysis) -> int:
    """Caras con problema según el criterio del fotógrafo: ojos cerrados o
    cara virada (no mira a cámara). Solo cuenta sobre caras que MediaPipe
    validó — las detecciones basura de YuNet (decoración) no suman."""
    return a.closed_eyes_count + a.looking_away_count


def photos_for_coverage(
    identities_by_photo: dict[int, list[int]],
    selected: set[int],
    score_by_photo: dict[int, float],
) -> set[int]:
    """
    Garantía "al menos una buena foto de cada persona" (Fase L).

    Dada la identidad de las personas por foto, el conjunto ya seleccionado y el
    score de cada foto, devuelve las fotos a PROMOVER: para cada identidad que
    no tenga ninguna foto seleccionada, su foto de mayor score. No baja nada —
    solo suma cobertura.
    """
    cubiertas: set[int] = set()
    todas: set[int] = set()
    for idx, ids in identities_by_photo.items():
        todas.update(ids)
        if idx in selected:
            cubiertas.update(ids)

    promover: set[int] = set()
    for ident in todas - cubiertas:
        candidatas = [i for i, ids in identities_by_photo.items() if ident in ids]
        if candidatas:
            promover.add(max(candidatas, key=lambda i: score_by_photo.get(i, 0.0)))
    return promover


def apply_decision_logic(
    records: list[Any],
    analyses: list[PhotoAnalysis],
    clusters: list[ImageCluster],
    rep_scores: dict[int, float],
    trash_flags: list[bool],
    prefs: dict[str, Any],
    settings: dict[str, Any],
    develop_by_idx: dict[int, dict],
    all_scores: dict[int, float] | None = None,
) -> list[dict[str, Any]]:

    scores = all_scores if all_scores is not None else rep_scores
    KEEP_FRACTION = {"few": 0.40, "standard": 0.65, "more": 0.85}
    HIGHLIGHT_FRACTION = 0.10
    
    singleton_reps = [c.representative_index for c in clusters if len(c.image_indices) == 1]
    
    def _selectable(idx: int) -> bool:
        if records[idx].error:
            return False
        if trash_flags[idx] and prefs.get("detect_blurry", True):
            return False
        return True

    pool = sorted((i for i in singleton_reps if _selectable(i)),
                  key=lambda i: rep_scores[i], reverse=True)
    keep_frac = KEEP_FRACTION.get(prefs.get("selectivity_target", "standard"), 0.65)
    keep_n = max(1, int(round(len(pool) * keep_frac))) if pool else 0
    demoted = set(pool[keep_n:])

    final_selected = sorted(
        (i for i in rep_scores if _selectable(i) and i not in demoted),
        key=lambda i: rep_scores[i], reverse=True)
    highlights: set[int] = set()
    if prefs.get("detect_highlights", True) and final_selected:
        top_n = max(1, int(round(len(final_selected) * HIGHLIGHT_FRACTION)))
        highlights = set(final_selected[:top_n])

    ratings_map = settings.get("ratings_mapping", {})
    auto_crop_level = prefs.get("auto_crop", "minimo")
    results = []

    for cluster in clusters:
        if not cluster.image_indices:
            continue
        for idx in cluster.image_indices:
            if idx >= len(records):
                continue
            record = records[idx]
            is_representative = (idx == cluster.representative_index)
            is_trash = trash_flags[idx] if idx < len(trash_flags) else False

            # Descarte por caras: RELATIVO a la ganadora de su ráfaga. En una
            # grupal casi siempre hay alguien parpadeando o mirando a otro
            # lado, así que un criterio absoluto pintaría casi todo el evento.
            # Se marca la perdedora que tiene MÁS caras con problema (ojos
            # cerrados o virada) que la ganadora — "la peor de la grupal".
            # La política vive aquí (el análisis solo mide): apagar la casilla
            # no descarta el análisis, así que activarla es una re-selección
            # instantánea en vez de re-analizar el evento entero.
            rep = analyses[cluster.representative_index] if cluster.representative_index < len(analyses) else None
            a = analyses[idx] if idx < len(analyses) else None
            has_closed = bool(
                prefs.get("detect_closed_eyes", True)
                and a and rep and _bad_faces(a) > _bad_faces(rep)
            )

            if record.error:
                label = None
                stars = 0
            elif is_trash and prefs.get("detect_blurry", True):
                label = "blurry"
                stars = ratings_map.get("blurry", {}).get("stars", 1)
            elif has_closed and not is_representative:
                label = "closed_eyes"
                stars = ratings_map.get("closed_eyes", {}).get("stars", 1)
            elif is_representative and idx in demoted:
                label = "duplicates"
                stars = ratings_map.get("duplicates", {}).get("stars", 2)
            elif is_representative and idx in highlights:
                label = "highlighted"
                stars = ratings_map.get("highlighted", {}).get("stars", 5)
            elif is_representative:
                label = "selected"
                stars = ratings_map.get("selected", {}).get("stars", 4)
            else:
                label = "duplicates"
                stars = ratings_map.get("duplicates", {}).get("stars", 2)

            crop_dict = None
            if (label in ("selected", "highlighted") and auto_crop_level in LEVEL_LIMITS
                    and getattr(record, "thumb_ai", None) is not None):
                gray = cv2.cvtColor(record.thumb_ai, cv2.COLOR_RGB2GRAY)
                from services import person_detector
                persons = person_detector.detect_persons(record.thumb_ai)
                prop = propose_crop(
                    analyses[idx].scene_type, analyses[idx].face_bboxes, analyses[idx].eye_landmarks,
                    analyses[idx].saliency_region, record.thumb_ai.shape,
                    auto_crop_level, detect_horizon_angle(gray),
                    person_bboxes=persons, img_rgb=record.thumb_ai,
                )
                if prop is not None:
                    crop_dict = prop.to_dict()

            results.append({
                "path": record.path,
                "filename": record.filename,
                "is_raw": record.is_raw,
                "scene_type": analyses[idx].scene_type if idx < len(analyses) else "detail",
                "cluster_id": cluster.cluster_id,
                "is_cluster_representative": is_representative,
                "label": label,
                "stars": stars,
                "color": ratings_map.get(label, {}).get("color", "") if label else "",
                "blur_score": round(analyses[idx].blur_score, 2) if idx < len(analyses) else 0,
                "score": round(scores.get(idx, 0.0), 4),
                "crop": crop_dict,
                "has_crop": crop_dict is not None,
                "develop": develop_by_idx.get(idx) if label in ("selected", "highlighted") else None,
                "error": record.error,
            })
            
            if getattr(record, "linked_raw_path", None):
                import copy
                raw_res = copy.deepcopy(results[-1])
                raw_res["path"] = record.linked_raw_path
                raw_res["filename"] = Path(record.linked_raw_path).name
                raw_res["is_raw"] = True
                results.append(raw_res)

    return results, demoted, final_selected, highlights
