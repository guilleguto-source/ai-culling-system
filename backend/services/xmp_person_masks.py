"""
Lightroom Classic Native AI Person Mask Generator (XMP)
Genera el bloque crs:MaskGroupBasedCorrections con flag de re-cálculo en segundo plano.
Basado en la estructura interna extraída de Camera Raw.8bi.
"""

from enum import Enum
from typing import List, Optional
import uuid
import xml.etree.ElementTree as ET

class PersonSemanticLabel(str, Enum):
    """Categorías semánticas reconocidas por Camera Raw (postproc_panopticfcn)."""
    FACE_SKIN = "FaceSkin"
    BODY_SKIN = "BodySkin"
    EYEBROWS = "Eyebrows"
    EYE_SCLERA = "EyeSclera"
    IRIS_AND_PUPIL = "IrisAndPupil"
    LIPS = "Lips"
    TEETH = "Teeth"
    HAIR = "Hair"
    EARS = "Ears"
    BEARD = "Beard"
    CLOTHES = "Clothes"


class PersonMaskXMPBuilder:
    """Constructor del bloque XML para inyectar máscaras semánticas en metadatos XMP."""

    def __init__(self, correction_name: str = "Retoque IA Personas"):
        self.correction_name = correction_name
        self.masks: List[PersonSemanticLabel] = []

    def add_mask(self, label: PersonSemanticLabel) -> "PersonMaskXMPBuilder":
        if label not in self.masks:
            self.masks.append(label)
        return self

    def build_xml_snippet(self) -> str:
        """
        Produce el fragmento XML crs:MaskGroupBasedCorrections exacto
        con crs:Recompute="true" para forzar el cálculo en background de Lightroom.
        """
        sync_id = str(uuid.uuid4()).upper()

        mask_elements = []
        for mask_label in self.masks:
            mask_elements.append(f"""      <rdf:li
       crs:What="Mask/Aggregate"
       crs:MaskActive="true"
       crs:MaskInverted="false"
       crs:MaskBlendMode="0"
       crs:MaskValue="1.000000"
       crs:MaskVersion="1"
       crs:MaskSubType="fMaskSemanticLabel"
       crs:SemanticObjectPrompt="{mask_label.value}"
       crs:Recompute="true"
       crs:Feather="0.000000"
       crs:EdgeShift="0.000000"/>""")

        masks_body = "\n".join(mask_elements)

        xml = f"""<crs:MaskGroupBasedCorrections>
 <rdf:Seq>
  <rdf:li>
   <rdf:Description
    crs:What="Correction"
    crs:CorrectionAmount="1.000000"
    crs:CorrectionActive="true"
    crs:CorrectionName="{self.correction_name}"
    crs:CorrectionSyncID="{sync_id}">
    <crs:CorrectionMasks>
     <rdf:Seq>
{masks_body}
     </rdf:Seq>
    </crs:CorrectionMasks>
   </rdf:Description>
  </rdf:li>
 </rdf:Seq>
</crs:MaskGroupBasedCorrections>"""
        return xml


def inject_person_masks_into_xmp(existing_xmp: str, labels: List[PersonSemanticLabel]) -> str:
    """Inserta las máscaras de personas en un archivo XMP existente sin corromper otros tags."""
    builder = PersonMaskXMPBuilder()
    for l in labels:
        builder.add_mask(l)
    
    snippet = builder.build_xml_snippet()
    if "</rdf:Description>" in existing_xmp:
        return existing_xmp.replace("</rdf:Description>", f"{snippet}\n</rdf:Description>", 1)
    return existing_xmp + "\n" + snippet
