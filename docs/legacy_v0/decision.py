from __future__ import annotations
from .types import PhotoMetrics, Decision
from .presets import Preset


def is_blurry(p: PhotoMetrics, preset: Preset) -> bool:
    """Borrosa si la nitidez global es baja Y no hay ninguna región nítida (anti-bokeh)."""
    if p.sharpness_global >= preset.blur_threshold:
        return False
    return p.salient_sharpness < preset.salient_threshold


def photo_score(p: PhotoMetrics, preset: Preset) -> float:
    w = preset.weights

    def nsharp(v: float) -> float:
        return min(1.0, v / preset.sharp_ref)

    # Media ponderada normalizada sobre los factores ACTIVOS (peso>0). Así activar o
    # desactivar un factor (p. ej. composición) no descalibra los umbrales: el score
    # sigue en 0..1. La nitidez del score usa la global (discrimina mejor que la
    # saliencia, que se satura); la saliencia solo decide borrosa (is_blurry).
    terms: list[tuple[float, float]] = [
        (w.get("sharp", 0.0), nsharp(p.sharpness_global)),
        (w.get("expo", 0.0), p.exposure_score),
        (w.get("dynamic_range", 0.0) if preset.use_dynamic_range else 0.0, p.dynamic_range),
        (w.get("composition", 0.0) if preset.use_composition else 0.0, p.composition),
    ]
    if p.has_faces:
        # Ponderar caras por área: el primer plano manda, no se diluye en multitudes.
        areas = [max(1, f.box[2] * f.box[3]) for f in p.faces]
        tot = sum(areas)
        terms += [
            (w.get("eye_sharp", 0.0),
             sum(nsharp(f.eye_sharpness) * a for f, a in zip(p.faces, areas)) / tot),
            (w.get("eyes_open", 0.0),
             sum(f.eye_aspect_ratio * a for f, a in zip(p.faces, areas)) / tot),
            (w.get("smile", 0.0),
             sum(f.smile_score * a for f, a in zip(p.faces, areas)) / tot),
        ]
    active = [(wt, v) for wt, v in terms if wt > 0]
    if not active:
        return 0.0
    return sum(wt * v for wt, v in active) / sum(wt for wt, _ in active)


def _keep_solo(p: PhotoMetrics, score: float, preset: Preset) -> bool:
    if score >= preset.keeper_threshold:
        return True
    return (not p.has_faces and preset.keep_detail_shots and p.exposure_score >= 0.5
            and not is_blurry(p, preset))


def decide(photos: list[PhotoMetrics], groups: list[list[int]], preset: Preset) -> list[Decision]:
    scores = [photo_score(p, preset) for p in photos]
    out: dict[int, Decision] = {}
    lab = preset.labels
    for group in groups:
        best = max(group, key=lambda i: scores[i])
        for i in group:
            p = photos[i]
            if is_blurry(p, preset):
                out[i] = Decision(p.path, lab["reject"], 0)            # borrosa de verdad
            elif i != best:
                out[i] = Decision(p.path, lab["reject"], 0)            # peor del grupo
            elif len(group) == 1 and not _keep_solo(p, scores[i], preset):
                out[i] = Decision(p.path, None, 0)                     # suelta neutra
            else:
                label = lab["highlight"] if scores[i] >= preset.highlight_threshold else lab["keeper"]
                out[i] = Decision(p.path, label, preset.stars_keeper)
    return [out[i] for i in range(len(photos))]
