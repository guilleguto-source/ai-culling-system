"""Tests del exportador XMP: embebido en JPEG (Python puro) y sidecar RAW."""
import io
from pathlib import Path

import numpy as np
from PIL import Image

from services import xmp_exporter as xe


def _make_jpeg(path: Path):
    arr = (np.random.default_rng(0).integers(0, 256, (64, 96, 3))).astype("uint8")
    Image.fromarray(arr).save(path, format="JPEG", quality=90)


def test_jpeg_embed_not_corrupt_and_readable(tmp_path):
    p = tmp_path / "img.jpg"
    _make_jpeg(p)
    assert xe.write_xmp(str(p), label="selected", stars=3, color="Verde") is True
    # El archivo sigue siendo un JPEG válido
    Image.open(p).verify()
    # El XMP es recuperable y contiene el rating y la etiqueta dinámica
    packet = xe._extract_jpeg_xmp(p.read_bytes())
    assert packet is not None
    assert b"<xmp:Rating>3</xmp:Rating>" in packet
    assert "Verde".encode() in packet
    assert xe.XMP_APP1_SIG not in packet  # la firma del segmento no va dentro del packet


def test_jpeg_custom_spanish_label(tmp_path):
    p = tmp_path / "p.jpg"
    _make_jpeg(p)
    xe.write_xmp(str(p), label="closed_eyes", stars=0, color="Púrpura")
    packet = xe._extract_jpeg_xmp(p.read_bytes())
    assert "Púrpura".encode() in packet


def test_jpeg_embed_idempotent_single_xmp(tmp_path):
    p = tmp_path / "i.jpg"
    _make_jpeg(p)
    xe.write_xmp(str(p), "selected", 3, "Verde", overwrite=True)
    xe.write_xmp(str(p), "blurry", 1, "Rojo", overwrite=True)
    data = p.read_bytes()
    # No debe haber dos segmentos APP1-XMP acumulados
    assert data.count(xe.XMP_APP1_SIG) == 1
    packet = xe._extract_jpeg_xmp(data)
    assert b"<xmp:Rating>1</xmp:Rating>" in packet and "Rojo".encode() in packet


def test_jpeg_overwrite_false_preserves(tmp_path):
    p = tmp_path / "o.jpg"
    _make_jpeg(p)
    xe.write_xmp(str(p), "selected", 3, "Verde", overwrite=True)
    # Con overwrite=False y rating existente -> no escribe
    assert xe.write_xmp(str(p), "blurry", 0, "Rojo", overwrite=False) is False
    packet = xe._extract_jpeg_xmp(p.read_bytes())
    assert b"<xmp:Rating>3</xmp:Rating>" in packet  # conserva el 3


def test_raw_writes_sidecar(tmp_path):
    raw = tmp_path / "shot.CR2"
    raw.write_bytes(b"\x00\x01fake-raw")
    assert xe.write_xmp(str(raw), "selected", 3, "Verde") is True
    sidecar = tmp_path / "shot.xmp"
    assert sidecar.exists()
    assert "Verde".encode() in sidecar.read_bytes()
    # No debe tocar (embeber) el RAW
    assert raw.read_bytes() == b"\x00\x01fake-raw"
