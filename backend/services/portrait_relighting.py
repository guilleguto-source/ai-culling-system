"""
portrait_relighting.py — Módulo de Re-iluminación Facial (Fase 3).

Estima la ubicación y luminosidad de los rostros detectados en la imagen
y genera ajustes locales y máscaras paramétricas para realzar la iluminación
del sujeto principal sin quemar el fondo.
"""
import logging
from dataclasses import dataclass
from typing import Any
from lxml import etree

logger = logging.getLogger(__name__)

NS_CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


@dataclass
class FaceRelightProposal:
    face_index: int
    center_x: float  # [0..1]
    center_y: float  # [0..1]
    radius_x: float  # [0..1]
    radius_y: float  # [0..1]
    exposure_boost: float  # e.g. +0.25 to +0.60 EV
    highlights_boost: int  # e.g. +10
    shadows_lift: int  # e.g. +15


def calculate_face_relighting(
    face_bboxes: list[list[int]],
    img_width: int = 1920,
    img_height: int = 1080,
    intensity: float = 0.5,
) -> list[FaceRelightProposal]:
    """
    Calcula propuestas de re-iluminación para los rostros detectados.
    face_bboxes: lista de [x, y, w, h]
    intensity: escala de 0.0 a 1.0 (control del usuario)
    """
    if not face_bboxes or img_width <= 0 or img_height <= 0:
        return []

    proposals = []
    intensity_clamped = max(0.1, min(1.0, float(intensity)))

    for i, bbox in enumerate(face_bboxes):
        x, y, w, h = bbox
        cx = (x + w / 2.0) / img_width
        cy = (y + h / 2.0) / img_height
        rx = (w * 0.9) / img_width
        ry = (h * 1.1) / img_height

        exp_boost = round(0.40 * intensity_clamped, 2)
        hi_boost = int(round(15 * intensity_clamped))
        sh_lift = int(round(25 * intensity_clamped))

        proposals.append(
            FaceRelightProposal(
                face_index=i,
                center_x=round(cx, 4),
                center_y=round(cy, 4),
                radius_x=round(rx, 4),
                radius_y=round(ry, 4),
                exposure_boost=exp_boost,
                highlights_boost=hi_boost,
                shadows_lift=sh_lift,
            )
        )

    return proposals


def build_relighting_xmp_elements(proposals: list[FaceRelightProposal]) -> list[Any]:
    """
    Construye los elementos XML de correcciones locales (PaintBasedCorrections / Radial)
    compatibles con Adobe Camera Raw / Lightroom.
    """
    if not proposals:
        return []

    elements = []
    corrections_el = etree.Element(f"{{{NS_CRS}}}PaintBasedCorrections")
    seq_el = etree.SubElement(corrections_el, f"{{{NS_RDF}}}Seq")

    for p in proposals:
        li_el = etree.SubElement(seq_el, f"{{{NS_RDF}}}li")
        desc_el = etree.SubElement(li_el, f"{{{NS_RDF}}}Description")
        desc_el.set(f"{{{NS_CRS}}}What", "Correction")
        desc_el.set(f"{{{NS_CRS}}}CorrectionAmount", "1.000000")
        desc_el.set(f"{{{NS_CRS}}}LocalExposure2012", f"{p.exposure_boost:+.4f}")
        desc_el.set(f"{{{NS_CRS}}}LocalHighlights2012", f"{p.highlights_boost:+d}")
        desc_el.set(f"{{{NS_CRS}}}LocalShadows2012", f"{p.shadows_lift:+d}")

    elements.append(corrections_el)
    return elements
