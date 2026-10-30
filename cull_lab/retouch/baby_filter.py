"""
CullLab Newborn Protection & Baby Acne Filter
Inspirado en el módulo FaceAcneBaby de Evoto AI.
Distingue imperfecciones removibles de pliegues anatómicos, marcas de nacimiento y rojeces naturales de recién nacidos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class BlemishCandidate:
    """Candidato a imperfección o mancha dérmica detectada."""
    id: str
    center_x: float           # [0, 1]
    center_y: float           # [0, 1]
    radius_px: float          # Radio estimado de la mancha
    contrast: float           # Diferencia relativa de luminancia respecto a la piel [0, 1]
    eccentricity: float       # 0 = círculo perfecto, 1 = línea alargada (pliegue)
    is_diffuse_redness: bool  # Rojeces fisiológicas difusas


@dataclass
class FilteredBlemish:
    """Resultado del filtro con veredicto de eliminación."""
    candidate: BlemishCandidate
    should_remove: bool
    rejection_reason: str = "" # Razón por la cual se protegió (ej. 'newborn_crease')


class BabyAcneFilter:
    """
    Filtro de decisión dérmica con modo segregado para fotografía newborn/infantil.
    """

    def __init__(
        self,
        adult_contrast_threshold: float = 0.08,  # Umbral adulto para manchas
        baby_contrast_threshold: float = 0.35,   # Umbral bebé (solo manchas muy contrastadas como pelusas)
        max_fold_eccentricity: float = 0.65,     # Candidatos alargados son pliegues anatómicos
    ):
        self.adult_thresh = adult_contrast_threshold
        self.baby_thresh = baby_contrast_threshold
        self.max_fold_eccentricity = max_fold_eccentricity

    def filter_blemishes(
        self,
        candidates: Sequence[BlemishCandidate],
        is_baby_mode: bool = False,
    ) -> List[FilteredBlemish]:
        """
        Filtra candidatos a eliminar.
        En modo bebé, protege estrictamente pliegues, marcas de nacimiento y rojeces suaves.
        """
        results: List[FilteredBlemish] = []

        for cand in candidates:
            # 1. Modo Bebé (Newborn Protection)
            if is_baby_mode:
                # Regla A: Proteger pliegues naturales de piel (alta excentricidad / forma de surco)
                if cand.eccentricity >= self.max_fold_eccentricity:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=False,
                        rejection_reason="newborn_anatomical_fold",
                    ))
                    continue

                # Regla B: Proteger rojeces difusas naturales (eritema / calor / rubor)
                if cand.is_diffuse_redness and cand.contrast < self.baby_thresh:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=False,
                        rejection_reason="newborn_natural_erythema",
                    ))
                    continue

                # Regla C: En bebés solo se eliminan partículas extrañas de alto contraste (pelusa, suciedad)
                if cand.contrast >= self.baby_thresh:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=True,
                    ))
                else:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=False,
                        rejection_reason="newborn_low_contrast_protected",
                    ))

            # 2. Modo Adulto estándar
            else:
                # Pliegues pronunciados se conservan (arrugas estructurales)
                if cand.eccentricity >= 0.85:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=False,
                        rejection_reason="adult_expression_line",
                    ))
                elif cand.contrast >= self.adult_thresh:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=True,
                    ))
                else:
                    results.append(FilteredBlemish(
                        candidate=cand,
                        should_remove=False,
                        rejection_reason="below_contrast_threshold",
                    ))

        return results
