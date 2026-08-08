import cv2
from typing import Any
from pathlib import Path
from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.auto_crop import LEVEL_LIMITS, propose_crop, detect_horizon_angle


def _bad_faces(a: PhotoAnalysis) -> int:
    """Caras con problema según el criterio del fotógrafo: ojos cerrados o cara
    virada (no mira a cámara). Usa los CONTEOS ya refinados (analyze_photo +
    clasificador aprendido de Fase G3), no re-umbraliza face_attrs: derivar de
    nuevo con cortes fijos descartaría lo que el modelo aprendió del usuario."""
    return a.closed_eyes_count + a.looking_away_count


def build_reasons(
    idx: int,
    is_representative: bool,
    analyses: list[PhotoAnalysis],
    rep_index: int,
    gate_reasons: dict[int, str],
    decided_by: dict[int, str],
    solo_en_cluster: bool,
) -> list[str]:
    """
    Motivos legibles de por qué esta foto ganó o perdió su ráfaga.

    Solo afirma hechos que el sistema midió. En particular NO dice "mejor score"
    cuando quien decidió fue un gate técnico: la ganadora puede tener un score
    menor que una alternativa descartada, y afirmar lo contrario es falso.
    """
    if solo_en_cluster:
        return []

    a = analyses[idx] if idx < len(analyses) else None
    rep = analyses[rep_index] if rep_index < len(analyses) else None
    razones: list[str] = []

    if is_representative:
        criterio = decided_by.get(idx, "score")
        razones.append({
            "gate": "✔ Única sin defectos técnicos de la ráfaga",
            "gusto": "✔ La que más se parece a lo que sueles elegir",
            "score": "✔ Mejor combinación de nitidez y composición",
            "vlm": "✔ Elegida por IA visual profunda para desempatar (mejor expresión)",
            "elo": "✔ Desempate ELO: mejor combinación de expresión y nitidez relativa",
        }.get(criterio, "✔ Elegida de la ráfaga"))
        if a and a.valid_face_count:
            if not a.closed_eyes_count:
                razones.append("✔ Todos con los ojos abiertos")
            if a.smiling_count:
                razones.append(f"✔ {a.smiling_count} sonriendo")
        return razones

    # Perdedoras: primero el gate que la sacó (es el motivo real).
    motivo = gate_reasons.get(idx)
    if motivo == "ojos_cerrados":
        razones.append("✖ Ojos cerrados (hay alternativa con ojos abiertos)")
    elif motivo == "rostro_blando":
        razones.append("✖ Rostro menos nítido que el resto de la ráfaga")

    # Hechos comparativos contra la ganadora.
    if a and rep:
        if a.closed_eyes_count > rep.closed_eyes_count and motivo != "ojos_cerrados":
            razones.append(f"✖ {a.closed_eyes_count} con ojos cerrados")
        if a.looking_away_count > rep.looking_away_count:
            razones.append(f"✖ {a.looking_away_count} mirando fuera de cámara")
        if not razones and a.blur_score < rep.blur_score:
            razones.append("✖ Menos nítida que la elegida")
    return razones or ["Alternativa válida — la elegida puntuó algo mejor"]


def photos_for_group_coverage(
    identities_by_photo: dict[int, list[int]],
    selected: set[int],
    score_by_photo: dict[int, float],
) -> set[int]:
    """
    Fase 6: Garantía de Grupos Únicos.
    Identifica combinaciones únicas de personas (frozensets de tamaño >= 2) y
    personas individuales, y promueve la mejor foto de los grupos/personas
    que no hayan salido ya en las selecciones base.
    """
    from collections import Counter
    
    counts = Counter(i for ids in identities_by_photo.values() for i in ids)
    
    # 1. Identificar grupos (tamaño >= 2)
    grupos_por_foto: dict[int, frozenset] = {}
    for idx, ids in identities_by_photo.items():
        if len(ids) >= 2:
            grupos_por_foto[idx] = frozenset(ids)
            
    cubiertos: set[frozenset] = {grupos_por_foto[i] for i in selected if i in grupos_por_foto}
    todos_los_grupos = set(grupos_por_foto.values())
    
    promover: set[int] = set()
    # 2. Para cada grupo no cubierto, rescatar la mejor
    for g in todos_los_grupos - cubiertos:
        candidatas = [i for i, gr in grupos_por_foto.items() if gr == g]
        if candidatas:
            promover.add(max(candidatas, key=lambda i: score_by_photo.get(i, 0.0)))
            
    # 3. Cobertura de personas individuales (fallback de seguridad)
    personas_cubiertas = {p for i in (selected | promover) for p in identities_by_photo.get(i, [])}
    todas_las_personas = set(counts.keys())
    
    for p in todas_las_personas - personas_cubiertas:
        cands = [i for i, ids in identities_by_photo.items() if p in ids]
        if cands:
            promover.add(max(cands, key=lambda i: score_by_photo.get(i, 0.0)))
            
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
    gate_reasons: dict[int, str] | None = None,
    decided_by: dict[int, str] | None = None,
    margins: dict[int, float] | None = None,
) -> list[dict[str, Any]]:

    scores = all_scores if all_scores is not None else rep_scores
    gate_reasons = gate_reasons or {}
    decided_by = decided_by or {}
    margins = margins or {}
    KEEP_FRACTION = {"few": 0.35, "standard": 0.55, "more": 0.75}
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
    keep_frac = KEEP_FRACTION.get(prefs.get("selectivity_target", "standard"), 0.55)
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
    auto_crop_level = prefs.get("auto_crop", "off")
    # Enderezado desacoplado del crop: medido, el detector de horizonte erraba
    # 4.8° vs 1.3° del usuario y torcía el 80% de sus fotos derechas. Off por
    # defecto aunque el crop esté activo.
    auto_straighten = prefs.get("auto_straighten", False)
    
    from services.crop_style import load_crop_style
    learned_crop_style = load_crop_style()
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
                horizonte = detect_horizon_angle(gray) if auto_straighten else None
                prop = propose_crop(
                    analyses[idx].scene_type, analyses[idx].face_bboxes, analyses[idx].eye_landmarks,
                    analyses[idx].saliency_region, record.thumb_ai.shape,
                    auto_crop_level, horizonte,
                    person_bboxes=persons, img_rgb=record.thumb_ai,
                    crop_style=learned_crop_style,
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
                "diagnostics": {
                    "aesthetic_score": round(analyses[idx].aesthetic_score, 4) if idx < len(analyses) else 0.5,
                    "valid_face_count": analyses[idx].valid_face_count if idx < len(analyses) else 0,
                    "closed_eyes_count": analyses[idx].closed_eyes_count if idx < len(analyses) else 0,
                    "looking_away_count": analyses[idx].looking_away_count if idx < len(analyses) else 0,
                    "smiling_count": analyses[idx].smiling_count if idx < len(analyses) else 0
                },
                "reasons": build_reasons(
                    idx, is_representative, analyses, cluster.representative_index,
                    gate_reasons, decided_by,
                    solo_en_cluster=len(cluster.image_indices) <= 1,
                ),
                "decided_by": decided_by.get(cluster.representative_index, ""),
                # Margen chico = decisión reñida → candidata a repaso (Fase S)
                "margin": margins.get(idx, 1.0),
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
