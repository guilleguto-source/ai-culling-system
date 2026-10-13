from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class FaceMetrics:
    box: tuple[int, int, int, int]   # x, y, w, h
    eye_aspect_ratio: float          # eyes_open_score 0..1 (1 = ojos abiertos con certeza)
    eye_sharpness: float             # varianza Laplaciano sobre la cara
    smile_score: float               # prob de sonrisa/alegría 0..1 (HSC)

@dataclass
class PhotoMetrics:
    path: Path                       # archivo primario de la unidad
    timestamp: float                 # epoch segundos (EXIF o mtime)
    sharpness_global: float
    exposure_score: float            # 0..1 (1 = bien expuesta)
    phash: int                       # hash perceptual de 64 bits
    salient_sharpness: float = 0.0   # máx nitidez por tile (rescate anti-bokeh)
    dynamic_range: float = 0.0       # riqueza tonal 0..1 (entropía)
    composition: float = 0.0         # 0..1 (tercios + horizonte)
    faces: list[FaceMetrics] = field(default_factory=list)
    companions: list[Path] = field(default_factory=list)  # archivos hermanos (RAW+JPG)

    @property
    def has_faces(self) -> bool:
        return len(self.faces) > 0

@dataclass(frozen=True)
class Decision:
    path: Path
    label: str | None                # "Green" | "Blue" | "Red" | None
    rating: int                      # estrellas 0..5
