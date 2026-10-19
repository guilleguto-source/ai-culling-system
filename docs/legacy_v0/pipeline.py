from __future__ import annotations
from pathlib import Path
from . import loader, grouping, decision
from .analysis import sharpness, exposure, embedding, faces, eyes, expression, composition
from .types import PhotoMetrics, FaceMetrics, Decision
from .presets import Preset


def analyze_photo(path: Path, source: Path | None = None) -> PhotoMetrics:
    """Analiza `source` (o `path` si no se da) y registra el resultado bajo `path`."""
    src = source or path
    img = loader.load_image(src)
    face_metrics: list[FaceMetrics] = []
    for face in faces.detect_faces(img):
        open_score = eyes.eyes_open_score(img, face.right_eye, face.left_eye, face.box[2])
        face_metrics.append(FaceMetrics(
            box=face.box,
            eye_aspect_ratio=open_score,          # eyes_open_score 0..1
            eye_sharpness=sharpness.eye_region_sharpness(
                img, face.right_eye, face.left_eye, face.box[2]),
            smile_score=expression.smile_score(img, face.box),
        ))
    return PhotoMetrics(
        path=path,
        timestamp=loader.capture_timestamp(src),
        sharpness_global=sharpness.global_sharpness(img),
        exposure_score=exposure.exposure_score(img),
        phash=embedding.phash(img),
        salient_sharpness=sharpness.salient_sharpness(img),
        dynamic_range=exposure.dynamic_range(img),
        composition=composition.composition_score(img, [f.box for f in face_metrics]),
        faces=face_metrics,
    )


def _analyze_units(folder: Path, preset: Preset):
    """Núcleo compartido: devuelve (units, photos, groups, scores, decisions)."""
    units = loader.discover_units(folder)
    photos = [analyze_photo(primary, source) for primary, _comps, source in units]
    for pm, (_primary, comps, _source) in zip(photos, units):
        pm.companions = comps
    groups = grouping.group_bursts(photos, preset)
    scores = [decision.photo_score(p, preset) for p in photos]
    decisions = decision.decide(photos, groups, preset)
    return units, photos, groups, scores, decisions


def cull_folder(folder: Path, preset: Preset) -> list[Decision]:
    """Devuelve una Decision por ARCHIVO (primary + cada companion comparten etiqueta)."""
    _units, photos, _groups, _scores, decisions = _analyze_units(folder, preset)
    expanded: list[Decision] = []
    for d, pm in zip(decisions, photos):
        expanded.append(d)
        for companion in pm.companions:
            expanded.append(Decision(companion, d.label, d.rating))
    return expanded


def cull_report(folder: Path, preset: Preset) -> list[dict]:
    """Reporte detallado por foto (unidad) para diagnóstico y calibración."""
    _units, photos, groups, scores, decisions = _analyze_units(folder, preset)
    group_size = {i: len(g) for g in groups for i in g}
    records: list[dict] = []
    for i, (pm, d) in enumerate(zip(photos, decisions)):
        eyes_open = min((f.eye_aspect_ratio for f in pm.faces), default=None)
        if decision.is_blurry(pm, preset):
            reason = "blur"
        elif d.label == preset.labels["reject"]:
            reason = "worst_of_group"
        elif d.label == preset.labels["highlight"]:
            reason = "highlight"
        elif d.label == preset.labels["keeper"]:
            reason = "keeper"
        else:
            reason = "neutral"
        records.append({
            "path": str(pm.path),
            "label": d.label,
            "rating": d.rating,
            "reason": reason,
            "score": round(scores[i], 3),
            "sharpness_global": round(pm.sharpness_global, 1),
            "exposure": round(pm.exposure_score, 3),
            "dynamic_range": round(pm.dynamic_range, 3),
            "composition": round(pm.composition, 3),
            "n_faces": len(pm.faces),
            "eyes_open": round(eyes_open, 3) if eyes_open is not None else None,
            "group_size": group_size.get(i, 1),
            "companions": [c.name for c in pm.companions],
        })
    return records
