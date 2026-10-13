import pytest
from pathlib import Path
from lxml import etree

from services.xmp_exporter import (
    write_xmp,
    patch_xmp_metadata,
    read_raw_packet,
    NS,
)
from services.xmp_reader import has_lightroom_edits, read_xmp
from services.export_snapshot import save_snapshot, load_snapshot
from routers.tools import import_selection, ImportSelectionRequest


@pytest.fixture
def tmp_session(tmp_path):
    img1 = tmp_path / "photo_a.cr2"
    img2 = tmp_path / "photo_b.cr2"
    img3 = tmp_path / "photo_c.cr2"
    for img in (img1, img2, img3):
        img.write_bytes(b"\x00" * 100)
    return tmp_path, img1, img2, img3


def test_has_lightroom_edits_detection(tmp_session):
    tmp_path, img1, img2, img3 = tmp_session

    # Caso 1: Sin XMP -> False
    assert not has_lightroom_edits(str(img1))

    # Caso 2: Creado por Guto Flow -> False
    write_xmp(
        str(img1),
        label="selected",
        stars=3,
        color="Green",
        develop={"Exposure2012": 0.5},
        overwrite=True,
    )
    assert not has_lightroom_edits(str(img1))

    # Caso 3: Creado / modificado por Lightroom con ajustes manuales -> True
    xmp_lr = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000 1.000000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:ProcessVersion="15.4"
    crs:Exposure2012="+1.25"
    crs:Temperature="6500"
    crs:HasSettings="True">
   <xmp:Rating>2</xmp:Rating>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    xmp_file2 = tmp_path / "photo_b.xmp"
    xmp_file2.write_text(xmp_lr, encoding="utf-8")
    assert has_lightroom_edits(str(img2))


def test_patch_xmp_metadata_preserves_crs(tmp_session):
    tmp_path, _, img2, _ = tmp_session
    xmp_lr = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Exposure2012="+1.75"
    crs:Temperature="5200"
    crs:HasSettings="True">
   <crs:CustomCurve>0, 0, 255, 255</crs:CustomCurve>
   <xmp:Rating>1</xmp:Rating>
   <xmp:Label>Blue</xmp:Label>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    (tmp_path / "photo_b.xmp").write_text(xmp_lr, encoding="utf-8")

    # Parchamos solo metadatos de selección
    ok = patch_xmp_metadata(str(img2), label="selected", stars=4, color="Red", flag="pick")
    assert ok

    # Verificamos que se actualizaron Rating y Label
    data = read_xmp(str(img2), full=True)
    assert data["stars"] == 4
    assert data["color"] == "Red"
    assert data["develop"]["Exposure2012"] == 1.75
    assert data["develop"]["Temperature"] == 5200.0

    # Verificamos que el XML conserva crs:CustomCurve
    raw = read_raw_packet(str(img2))
    assert b"CustomCurve" in raw
    assert b"Adobe XMP Core" in raw


def test_write_xmp_guards_lightroom_edits(tmp_session):
    tmp_path, _, img2, _ = tmp_session
    xmp_lr = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Exposure2012="+2.00"
    crs:HasSettings="True">
   <xmp:Rating>1</xmp:Rating>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    (tmp_path / "photo_b.xmp").write_text(xmp_lr, encoding="utf-8")

    # Si Guto Flow intenta escribir sus propios filtros/revelado (Exposure2012=-0.50):
    ok = write_xmp(
        str(img2),
        label="selected",
        stars=5,
        color="Purple",
        develop={"Exposure2012": -0.50, "IncrementalTemperature": 10},
        crop={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9},
        overwrite=True,
    )
    assert ok

    # La foto debe tener el nuevo rating pero CONSERVAR la exposición de Lightroom (+2.00)
    data = read_xmp(str(img2), full=True)
    assert data["stars"] == 5
    assert data["color"] == "Purple"
    assert data["develop"]["Exposure2012"] == 2.00
    assert not data.get("crop")


def test_import_selection_merges_without_dropping(tmp_session):
    tmp_path, img1, img2, img3 = tmp_session

    # Estado inicial: Guto seleccionó photo_a, descartó photo_b y photo_c
    init_results = [
        {"path": str(img1), "label": "selected"},
        {"path": str(img2), "label": "blurry"},
        {"path": str(img3), "label": "blurry"},
    ]
    save_snapshot(str(tmp_path), init_results)
    write_xmp(str(img1), label="selected", stars=3, color="Green", flag="pick", overwrite=True)

    # El cliente escoge únicamente photo_b
    req = ImportSelectionRequest(
        base_dir=str(tmp_path),
        filenames=["photo_b.cr2"]
    )
    res = import_selection(req)
    assert res["status"] == "ok"
    assert res["updated"] == 1

    # Verificación de FUSIÓN (Guto ∪ Cliente):
    # 1. photo_b (elegida por el cliente) fue promovida a 4★/Red
    data_b = read_xmp(str(img2))
    assert data_b["stars"] == 4
    assert data_b["color"] == "Red"

    # 2. photo_a (elegida por Guto pero NO por cliente) SIGUE seleccionada con 3★/Green intacto
    data_a = read_xmp(str(img1))
    assert data_a["stars"] == 3
    assert data_a["color"] == "Green"

    # 3. Snapshot ahora contiene ambas como seleccionadas
    snap = load_snapshot(str(tmp_path))
    assert snap["items"][str(img1)] == "selected"
    assert snap["items"][str(img2)] == "selected"


def test_patch_pick_no_duplicate(tmp_session):
    tmp_path, _, img2, _ = tmp_session
    # XMP original que tiene crs:Pick como atributo
    xmp_lr = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Pick="0"
    crs:Exposure2012="+1.00">
   <xmp:Rating>1</xmp:Rating>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    (tmp_path / "photo_b.xmp").write_text(xmp_lr, encoding="utf-8")

    ok = patch_xmp_metadata(str(img2), label="selected", flag="pick")
    assert ok

    raw = read_raw_packet(str(img2))
    # No debe existir crs:Pick=" en los atributos
    assert b'crs:Pick="' not in raw
    # Debe existir como elemento hijo exactamente una vez
    assert raw.count(b"<crs:Pick>1</crs:Pick>") == 1
    assert raw.count(b"<xmp:Pick>1</xmp:Pick>") == 1


def test_import_selection_finds_outside_snapshot(tmp_session):
    tmp_path, img1, img2, img3 = tmp_session

    # Snapshot solo conoce photo_a y photo_b
    save_snapshot(str(tmp_path), [
        {"path": str(img1), "label": "selected"},
        {"path": str(img2), "label": "blurry"},
    ])

    # El cliente escoge photo_c (que NO está en el snapshot pero sí existe en disco)
    req = ImportSelectionRequest(
        base_dir=str(tmp_path),
        filenames=["photo_c.cr2"]
    )
    res = import_selection(req)
    assert res["status"] == "ok"
    assert res["updated"] == 1
    assert res["not_found"] == 0

    # photo_c fue encontrada vía rglob y promovida
    data_c = read_xmp(str(img3))
    assert data_c["stars"] == 4
    assert data_c["color"] == "Red"

    # Y registrada en el snapshot
    snap = load_snapshot(str(tmp_path))
    assert snap["items"][str(img3)] == "selected"

