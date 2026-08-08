"""
skin_retouch.py — Módulo de Retoque y Suavizado de Piel (Fase 3).

Detecta regiones de piel y propone ajustes paramétricos suaves (reducción de claridad local,
micro-contraste y aumento sutil de luminancia) para dar un acabado profesional no destructivo.
"""
import logging
from dataclasses import dataclass
from typing import Any
from lxml import etree

logger = logging.getLogger(__name__)

NS_CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


@dataclass
class SkinRetouchProposal:
    smoothness: float  # [0.0..1.0]
    local_clarity: int  # e.g. -25
    local_texture: int  # e.g. -15
    local_luminance: int  # e.g. +5
    skin_detected: bool


def calculate_skin_retouch(
    has_skin: bool = True,
    smoothness: float = 0.5,
) -> SkinRetouchProposal:
    """
    Calcula la propuesta de retoque de piel paramétrico.
    smoothness: escala de 0.0 a 1.0 (control del usuario)
    """
    if not has_skin:
        return SkinRetouchProposal(
            smoothness=0.0,
            local_clarity=0,
            local_texture=0,
            local_luminance=0,
            skin_detected=False,
        )

    s = max(0.1, min(1.0, float(smoothness)))
    clarity = int(round(-35 * s))
    texture = int(round(-20 * s))
    lum = int(round(8 * s))

    return SkinRetouchProposal(
        smoothness=round(s, 2),
        local_clarity=clarity,
        local_texture=texture,
        local_luminance=lum,
        skin_detected=True,
    )


def build_skin_retouch_xmp_elements(proposal: SkinRetouchProposal) -> list[Any]:
    """
    Construye los elementos XML de corrección local de piel.
    """
    if not proposal.skin_detected or proposal.local_clarity == 0:
        return []

    elements = []
    corrections_el = etree.Element(f"{{{NS_CRS}}}PaintBasedCorrections")
    seq_el = etree.SubElement(corrections_el, f"{{{NS_RDF}}}Seq")

    li_el = etree.SubElement(seq_el, f"{{{NS_RDF}}}li")
    desc_el = etree.SubElement(li_el, f"{{{NS_RDF}}}Description")
    desc_el.set(f"{{{NS_CRS}}}What", "Correction")
    desc_el.set(f"{{{NS_CRS}}}CorrectionAmount", "1.000000")
    desc_el.set(f"{{{NS_CRS}}}LocalClarity2012", f"{proposal.local_clarity:+d}")
    desc_el.set(f"{{{NS_CRS}}}LocalTexture", f"{proposal.local_texture:+d}")
    desc_el.set(f"{{{NS_CRS}}}LocalLuminanceNoise", f"{proposal.local_luminance:+d}")

    elements.append(corrections_el)
    return elements
