import logging
import cv2
import numpy as np
from typing import Any
from pathlib import Path
from services.analysis import PhotoAnalysis
from services.clustering import ImageCluster
from services.auto_crop import LEVEL_LIMITS, propose_crop, detect_horizon_angle

logger = logging.getLogger(__name__)

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
    exact_duplicates: dict[int, int] | None = None,
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

    if exact_duplicates and idx in exact_duplicates:
        razones.append("✖ Duplicado idéntico / cuasi-idéntico de ráfaga")

    # Perdedoras: primero el gate que la sacó (es el motivo real).
    motivo = gate_reasons.get(idx)
    if motivo == "ojos_cerrados":
        razones.append("✖ Ojos cerrados (hay alternativa con ojos abiertos)")
    elif motivo == "rostro_blando":
        razones.append("✖ Rostro menos nítido que el resto de la ráfaga")
    elif motivo == "flash_misfire":
        razones.append("✖ Disparo fallido de flash (ráfaga subexpuesta por falta de destello)")

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
    Fase 6: Garantía de Cobertura de Personas.
    Identifica personas que no hayan salido en NINGUNA foto de las selecciones base,
    y promueve la mejor foto de esa persona para que no quede excluida del evento.
    """
    from collections import Counter
    
    counts = Counter(i for ids in identities_by_photo.values() for i in ids)
    promovidas = set()
    
    # Personas ya cubiertas por la selección base
    personas_cubiertas = {p for i in selected for p in identities_by_photo.get(i, [])}
    
    # Para cada persona identificada en el evento (solo si es un "invitado real" recurrente)
    MIN_APPEARANCES = 3
    for p, count in counts.items():
        if count >= MIN_APPEARANCES and p not in personas_cubiertas:
            candidatos = [idx for idx, ids in identities_by_photo.items() if p in ids]
            if candidatos:
                candidatos.sort(key=lambda i: score_by_photo.get(i, 0.0), reverse=True)
                promovidas.add(candidatos[0])
                # Al promover esta foto, también cubrimos a otras personas que salgan en ella
                personas_cubiertas.update(identities_by_photo.get(candidatos[0], []))
                
    return promovidas


def trim_excess_to_target(
    final_selected_set: set[int],
    clusters: list[ImageCluster],
    scores: dict[int, float],
    records: list[Any],
    vip_photo_indices: set[int] | None = None,
    highlights: set[int] | None = None,
    coverage_promoted: set[int] | None = None,
    target_frac: float = 0.35,
    tolerance: float = 0.05,
) -> tuple[set[int], set[int]]:
    """
    Recorte Fino por Exceso:
    Si la cantidad de fotos seleccionadas supera la cuota objetivo por más de un 5%
    (target_frac + tolerance), degrada a 1 estrella ('alternative') las fotos de
    menor valor de ráfagas con múltiples selecciones, asegurando SIEMPRE al menos 1
    foto por ráfaga (el ganador del cluster nunca se degrada).

    Protecciones estrictas (nunca se degradan):
    - Singletons (clusters de 1 sola foto)
    - VIPs (fotos que contienen rostros de los protagonistas)
    - Highlights (fotos top 10%)
    - Cobertura (fotos promovidas para cobertura de persona)
    """
    n_total = len(records)
    if n_total == 0:
        return final_selected_set, set()

    cuota_target = int(round(n_total * target_frac))
    max_allowed = int(round(cuota_target * (1.0 + tolerance)))

    if len(final_selected_set) <= max_allowed:
        return final_selected_set, set()

    excess = len(final_selected_set) - cuota_target
    logger.info(
        f"[Trim] Exceso detectado: {len(final_selected_set)} seleccionadas > {max_allowed} "
        f"(target {cuota_target}, tolerancia +{tolerance*100:.0f}%). Buscando hasta {excess} alternativas."
    )

    vip_set = vip_photo_indices or set()
    high_set = highlights or set()
    cov_set = coverage_promoted or set()
    singleton_set = {c.image_indices[0] for c in clusters if len(c.image_indices) == 1}

    protected = vip_set | high_set | cov_set | singleton_set

    # Candidatas: en clusters con >= 2 fotos seleccionadas, todas menos la mejor
    candidates: list[int] = []
    for cluster in clusters:
        in_cluster_sel = [i for i in cluster.image_indices if i in final_selected_set]
        if len(in_cluster_sel) >= 2:
            winner = max(in_cluster_sel, key=lambda i: scores.get(i, 0.0))
            for i in in_cluster_sel:
                if i != winner and i not in protected:
                    candidates.append(i)

    # Ordenar candidatas de menor a mayor score (peores primero)
    candidates.sort(key=lambda i: scores.get(i, 0.0))

    demoted_to_alternative: set[int] = set()
    for cand in candidates:
        demoted_to_alternative.add(cand)
        excess -= 1
        if excess <= 0:
            break

    logger.info(
        f"[Trim] Se degradaron {len(demoted_to_alternative)} fotos de ráfaga a alternativa (1★). "
        f"Selección final ajustada: {len(final_selected_set - demoted_to_alternative)} fotos."
    )

    return final_selected_set - demoted_to_alternative, demoted_to_alternative


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
    exact_duplicates: dict[int, int] | None = None,
    identities_map: dict[int, list[int]] | None = None,
    vip_photo_indices: set[int] | None = None,
    chapter_map: dict[int, str] | None = None,
) -> tuple[list[dict[str, Any]], set[int], list[int], set[int]]:

    scores = all_scores if all_scores is not None else rep_scores
    gate_reasons = gate_reasons or {}
    decided_by = decided_by or {}
    margins = margins or {}
    exact_duplicates = exact_duplicates or {}
    vip_photo_indices = vip_photo_indices or set()

    # Umbral de calidad por nivel — controla fotos secundarias y ráfagas
    SCORE_THRESHOLD = {"few": 0.55, "standard": 0.42, "more": 0.30}
    HIGHLIGHT_FRACTION = 0.10

    def _selectable(idx: int) -> bool:
        if records[idx].error:
            return False
        if trash_flags[idx] and prefs.get("detect_blurry", True):
            return False
        return True

    def _is_horizontal(idx: int) -> bool:
        if idx >= len(records): return True
        return records[idx].width >= records[idx].height

    level = prefs.get("selectivity_target", "standard")
    threshold = SCORE_THRESHOLD.get(level, 0.42)

    # Normalización de Pacing por Capítulos
    chapter_scores: dict[str, list[float]] = {}
    for idx, sc in scores.items():
        if idx < len(records) and _selectable(idx):
            ch = chapter_map.get(idx, "capitulo_0") if chapter_map else "capitulo_0"
            chapter_scores.setdefault(ch, []).append(sc)

    chapter_medians: dict[str, float] = {}
    for ch, sc_list in chapter_scores.items():
        chapter_medians[ch] = float(np.median(sc_list)) if sc_list else 0.5

    all_valid_scores = [sc for sc_list in chapter_scores.values() for sc in sc_list]
    global_median = float(np.median(all_valid_scores)) if all_valid_scores else 0.5

    def _get_norm_score(idx: int) -> float:
        raw_score = scores.get(idx, 0.0)
        if not chapter_map or global_median <= 0:
            return raw_score
        ch = chapter_map.get(idx, "capitulo_0")
        ch_median = chapter_medians.get(ch, global_median)
        if ch_median <= 0.05:
            return raw_score
        # Escala relativa al capítulo (entre 0.7x y 1.4x)
        scale = max(0.7, min(1.4, global_median / ch_median))
        return raw_score * scale

    primary_reps = []
    secondary_reps = []

    for cluster in clusters:
        valid_in_cluster = [i for i in cluster.image_indices if _selectable(i)]
        if not valid_in_cluster:
            continue

        rep = cluster.representative_index
        if rep not in valid_in_cluster:
            rep = max(valid_in_cluster, key=lambda i: _get_norm_score(i))

        # ★ Supervivencia Obligatoria: el mejor de cada cluster SIEMPRE entra
        primary_reps.append(rep)

        # Orientación alternativa dentro del mismo cluster (horizontal/vertical)
        rep_is_horiz = _is_horizontal(rep)
        opp_orientation = [i for i in valid_in_cluster if i != rep and _is_horizontal(i) != rep_is_horiz]
        if opp_orientation:
            best_opp = max(opp_orientation, key=lambda i: _get_norm_score(i))
            if _get_norm_score(best_opp) >= threshold:
                secondary_reps.append(best_opp)

        # En modo indulgente ("more"), permitir variación adicional con alta calidad
        if level == "more":
            same_orientation = [i for i in valid_in_cluster if i != rep and _is_horizontal(i) == rep_is_horiz]
            if same_orientation:
                best_same = max(same_orientation, key=lambda i: _get_norm_score(i))
                if _get_norm_score(best_same) >= threshold * 1.15:
                    secondary_reps.append(best_same)

    final_selected_set = set(primary_reps) | set(secondary_reps)

    final_selected = sorted(list(final_selected_set), key=lambda i: scores.get(i, 0.0), reverse=True)
    highlights: set[int] = set()
    if prefs.get("detect_highlights", True) and final_selected:
        top_n = max(1, int(round(len(final_selected) * HIGHLIGHT_FRACTION)))
        highlights = set(final_selected[:top_n])

    # ★ Recorte Fino por Exceso: si la selección se pasa más de un 5% de la cuota
    target_frac = prefs.get("target_fraction")
    if target_frac is None:
        target_frac = {"few": 0.25, "standard": 0.35, "more": 0.50}.get(level, 0.35)

    final_selected_set, alternatives_set = trim_excess_to_target(
        final_selected_set=final_selected_set,
        clusters=clusters,
        scores=scores,
        records=records,
        vip_photo_indices=vip_photo_indices,
        highlights=highlights,
        coverage_promoted=None,
        target_frac=target_frac,
        tolerance=0.05,
    )

    demoted = set(i for c in clusters for i in c.image_indices if _selectable(i) and i not in final_selected_set and i not in alternatives_set)
    final_selected = sorted(list(final_selected_set), key=lambda i: scores.get(i, 0.0), reverse=True)

    ratings_map = settings.get("ratings_mapping", {})
    auto_crop_level = prefs.get("auto_crop", "off")
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
            elif has_closed and idx not in final_selected_set and idx not in alternatives_set:
                label = "closed_eyes"
                stars = ratings_map.get("closed_eyes", {}).get("stars", 1)
            elif idx in highlights:
                label = "highlighted"
                stars = ratings_map.get("highlighted", {}).get("stars", 5)
            elif idx in final_selected_set:
                label = "selected"
                stars = ratings_map.get("selected", {}).get("stars", 4)
            elif idx in alternatives_set:
                label = "alternative"
                stars = ratings_map.get("alternative", {}).get("stars", 1)
            else:
                label = "duplicates"
                stars = ratings_map.get("duplicates", {}).get("stars", 0)

            crop_dict = None
            if label in ("selected", "highlighted") and auto_crop_level in LEVEL_LIMITS:
                if getattr(record, "thumb_ai", None) is None:
                    try:
                        from services.thumbnail_store import read_thumbnail_from_disk
                        import io
                        from PIL import Image
                        duel_bytes = read_thumbnail_from_disk(record.path, "duel")
                        if duel_bytes:
                            img = Image.open(io.BytesIO(duel_bytes)).convert("RGB")
                            record.thumb_ai = np.array(img)
                    except Exception as e:
                        logger.error(f"Error loading thumb for crop on {record.path}: {e}")

                if getattr(record, "thumb_ai", None) is not None:
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
                record.thumb_ai = None  # Free memory

            photo_reasons = build_reasons(
                idx, (idx in final_selected_set or is_representative),
                analyses, cluster.representative_index,
                gate_reasons, decided_by,
                solo_en_cluster=len(cluster.image_indices) <= 1,
                exact_duplicates=exact_duplicates,
            )
            if idx in alternatives_set:
                photo_reasons.append("⚠ Reducida a alternativa (1★): cuota del nivel alcanzada (asegurando 1 por ráfaga)")
            elif idx in vip_photo_indices and idx in final_selected_set:
                photo_reasons.append("★ Protagonista VIP del evento")

            results.append({
                "path": record.path,
                "linked_raw_path": getattr(record, "linked_raw_path", None),
                "filename": record.filename,
                "is_raw": record.is_raw,
                "scene_type": analyses[idx].scene_type if idx < len(analyses) else "detail",
                "cluster_id": cluster.cluster_id,
                "is_cluster_representative": is_representative,
                "is_exact_duplicate": bool(exact_duplicates and idx in exact_duplicates),
                "duplicate_of": exact_duplicates.get(idx) if exact_duplicates else None,
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
                "reasons": photo_reasons,
                "decided_by": decided_by.get(cluster.representative_index, ""),
                "margin": margins.get(idx, 1.0),
                "crop": crop_dict,
                "has_crop": crop_dict is not None,
                "develop": develop_by_idx.get(idx) if label in ("selected", "highlighted") else None,
                "identity_ids": sorted(identities_map.get(idx, [])) if identities_map else [],
                "error": record.error,
                "chapter_id": chapter_map.get(idx, "capitulo_0") if chapter_map else "capitulo_0",
            })

    return results, demoted, final_selected, highlights
