"""
discrepancy_filter.py — Filtro de discrepancias para la Cascada 2-Pass de UniFace.
Identifica fotos que requieren re-análisis con el detector pesado (SCRFD-10G).
Incluye un Safety Cap para evitar tiempos excesivos en CPU.
"""
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional
from services.analysis import PhotoAnalysis

logger = logging.getLogger(__name__)

CASCADE_MIN_FACE_SIZE = 40
CASCADE_MAX_FACES_TRIGGER = 8
CASCADE_CONFIDENCE_THRESHOLD = 0.75


@dataclass
class DiscrepancyRule:
    name: str
    check: Callable[[PhotoAnalysis], bool]
    priority: int  # 1 = máxima prioridad, 5 = opcional


def _check_no_faces(a: PhotoAnalysis) -> bool:
    # 0 caras detectadas: podría ser paisaje O un grupo de espaldas/perfil/lejos
    return a.face_count == 0


def _check_crowd(a: PhotoAnalysis) -> bool:
    # Multitudes: 500M suele perder caras en los bordes o fondo
    return a.face_count >= CASCADE_MAX_FACES_TRIGGER


def _check_tiny_faces(a: PhotoAnalysis) -> bool:
    # Caras muy pequeñas (< 40px)
    for b in a.face_bboxes:
        if isinstance(b, (list, tuple)) and len(b) >= 4:
            if max(b[2], b[3]) < CASCADE_MIN_FACE_SIZE:
                return True
    return False


def _check_low_confidence(a: PhotoAnalysis) -> bool:
    # Caras dudosas o borrosas
    if a.face_count > 0:
        confs = []
        for attr in getattr(a, "face_attrs", []):
            if isinstance(attr, dict) and "confidence" in attr:
                confs.append(attr["confidence"])
        if confs and (sum(confs) / len(confs)) < CASCADE_CONFIDENCE_THRESHOLD:
            return True
    return False


DEFAULT_RULES: List[DiscrepancyRule] = [
    DiscrepancyRule("no_faces", _check_no_faces, 1),
    DiscrepancyRule("crowd_suspect", _check_crowd, 2),
    DiscrepancyRule("tiny_faces", _check_tiny_faces, 3),
    DiscrepancyRule("low_confidence", _check_low_confidence, 4),
]


def find_discrepancies(
    analyses: List[PhotoAnalysis],
    rules: Optional[List[DiscrepancyRule]] = None,
    max_discrepancy_ratio: float = 0.30,
) -> List[int]:
    """
    Retorna los índices de las fotos que deben enviarse al Pass 2 (SCRFD-10G).
    Aplica un Safety Cap (por defecto 30%) para proteger el rendimiento en CPU.
    """
    rules = rules or DEFAULT_RULES
    dudas = set()
    total = len(analyses)
    
    if total == 0:
        return []

    for rule in sorted(rules, key=lambda r: r.priority):
        for idx, a in enumerate(analyses):
            if a.error:
                continue
            if rule.check(a):
                dudas.add(idx)

    ratio = len(dudas) / total
    logger.info(f"DiscrepancyFilter: {len(dudas)}/{total} fotos dudosas detectadas ({ratio:.1%}).")

    # Safety Cap: Si más del max_discrepancy_ratio son dudosas, recortar por prioridad
    if ratio > max_discrepancy_ratio:
        cutoff = max(1, int(total * max_discrepancy_ratio))
        logger.warning(
            f"Safety Cap activado: reduciendo fotos para Pass 2 de {len(dudas)} a {cutoff} ({max_discrepancy_ratio:.1%})."
        )
        
        # Ponderar por cantidad de reglas disparadas
        scored = []
        for idx in dudas:
            a = analyses[idx]
            score = sum(1 for r in rules if r.check(a))
            # Dar más peso a fotos que no tienen caras
            if a.face_count == 0:
                score += 2
            scored.append((score, idx))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        dudas = {idx for _, idx in scored[:cutoff]}

    return sorted(list(dudas))
