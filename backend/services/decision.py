import cv2
from typing import Any
from pathlib import Path
from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.auto_crop import LEVEL_LIMITS, propose_crop, detect_horizon_angle

def apply_decision_logic(
    records: list[Any],
    analyses: list[PhotoAnalysis],
    clusters: list[ImageCluster],
    rep_scores: dict[int, float],
    trash_flags: list[bool],
    prefs: dict[str, Any],
    settings: dict[str, Any],
    develop_by_idx: dict[int, dict]
) -> list[dict[str, Any]]:
    
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

            # "Ojos cerrados" es RELATIVO a la ganadora de su ráfaga: en una
            # grupal casi siempre hay alguien parpadeando, así que marcar
            # cualquier foto con >=1 ojo cerrado pintaría el 97% del evento.
            # Solo se marca la perdedora que tiene MÁS caras con ojos cerrados
            # que la ganadora — la peor del grupo, que es lo que se descarta.
            rep = analyses[cluster.representative_index] if cluster.representative_index < len(analyses) else None
            a = analyses[idx] if idx < len(analyses) else None
            has_closed = bool(
                a and rep and a.closed_eyes_count > rep.closed_eyes_count
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
