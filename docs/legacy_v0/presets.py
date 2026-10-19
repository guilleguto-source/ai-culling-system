from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

BLUR_THRESHOLDS = {"indulgente": 25.0, "moderado": 45.0, "estricto": 70.0}


@dataclass(frozen=True)
class Preset:
    blur: str = "moderado"               # indulgente | moderado | estricto
    eyes_closed: str = "score_only"      # solo penaliza ranking
    duplicates: str = "stack"            # informativo; agrupado siempre activo
    stars_keeper: int = 3
    keep_detail_shots: bool = True
    use_dynamic_range: bool = False      # factor de rango dinámico (off por defecto)
    use_composition: bool = False        # factor de composición (off por defecto)
    ear_threshold: float = 0.5           # umbral sobre eyes_open_score (0..1)
    ocec_open: float = 0.58              # OCEC: prob_open >= -> abierto
    ocec_closed: float = 0.42            # OCEC: prob_open <= -> cerrado
    burst_time_window_s: float = 3.0
    phash_max_distance: int = 8
    keeper_threshold: float = 0.5
    highlight_threshold: float = 0.65
    salient_threshold: float = 60.0      # rescate anti-bokeh: nitidez por tile mínima (grid 8)
    sharp_ref: float = 300.0             # normaliza nitidez a 0..1
    labels: dict[str, str] = field(
        default_factory=lambda: {"keeper": "Green", "highlight": "Blue", "reject": "Red"})
    weights: dict[str, float] = field(
        default_factory=lambda: {"eye_sharp": 0.25, "sharp": 0.20, "expo": 0.15,
                                 "eyes_open": 0.20, "smile": 0.20,
                                 "dynamic_range": 0.10, "composition": 0.12})

    @property
    def blur_threshold(self) -> float:
        return BLUR_THRESHOLDS[self.blur]


def load_preset(path: Path | None) -> Preset:
    if path is None:
        return Preset()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Preset(**data)
