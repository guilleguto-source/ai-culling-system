from __future__ import annotations
import subprocess
from pathlib import Path
from .loader import is_raw

_XMP_TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:Rating>{rating}</xmp:Rating>{label}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def build_xmp(rating: int, label: str | None) -> str:
    label_xml = f"\n   <xmp:Label>{label}</xmp:Label>" if label else ""
    return _XMP_TEMPLATE.format(rating=rating, label=label_xml)


def write_metadata(path: Path, rating: int, label: str | None) -> None:
    """RAW -> sidecar .xmp; JPEG -> XMP embebido (solo metadatos, sin recomprimir)."""
    if is_raw(path):
        path.with_suffix(".xmp").write_text(build_xmp(rating, label), encoding="utf-8")
    else:
        _embed_jpeg(path, rating, label)


def _embed_jpeg(path: Path, rating: int, label: str | None) -> None:
    args = ["exiftool", "-overwrite_original", "-P", f"-XMP-xmp:Rating={rating}",
            f"-XMP-xmp:Label={label or ''}", str(path)]
    subprocess.run(args, check=True, capture_output=True)
