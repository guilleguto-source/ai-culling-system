"""
Tests de integración para el protocolo binario IPC de CullLab <-> LightCraft.
Valida:
1. Codificación y decodificación de headers binarios GTFL (16 bytes).
2. Protección contra magic bytes corruptos y versiones incompatibles.
3. Serialización/deserialización exacta de descriptores de memoria compartida (Zero-Copy).
4. Transporte de veredictos de culling con precisión flotante.
"""

import pytest

from cull_lab.bridge.ipc_protocol import (
    HEADER_SIZE,
    MAGIC_BYTES,
    PROTOCOL_VERSION,
    CullingVerdictPayload,
    LightCraftBridgeMessage,
    MessageType,
    PixelFormat,
    SharedBufferDescriptor,
)


def test_ipc_header_encode_decode():
    """Valida el empaquetado binario y desempaquetado de encabezados estándar."""
    dummy_payload = b"\x01\x02\x03\x04\x05"
    corr_id = 998877

    raw_msg = LightCraftBridgeMessage.encode(
        msg_type=MessageType.FRAME_READY_NOTIFICATION,
        correlation_id=corr_id,
        payload=dummy_payload,
    )

    assert len(raw_msg) == HEADER_SIZE + len(dummy_payload)

    msg_type, payload_len, decoded_corr_id = LightCraftBridgeMessage.decode_header(raw_msg)
    assert msg_type == MessageType.FRAME_READY_NOTIFICATION
    assert payload_len == len(dummy_payload)
    assert decoded_corr_id == corr_id


def test_ipc_header_validation_errors():
    """Valida rechazo explícito de cabeceras corruptas o incompletas."""
    # Cabecera truncada
    with pytest.raises(ValueError, match="Header incompleto"):
        LightCraftBridgeMessage.decode_header(b"GTFL\x01")

    # Magic inválido
    corrupt_magic = b"XXXX\x01\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    with pytest.raises(ValueError, match="Magic bytes inválidos"):
        LightCraftBridgeMessage.decode_header(corrupt_magic)

    # Versión no soportada
    bad_version = MAGIC_BYTES + b"\x99\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    with pytest.raises(ValueError, match="Versión de protocolo no soportada"):
        LightCraftBridgeMessage.decode_header(bad_version)


def test_shared_buffer_descriptor_roundtrip():
    """Valida la serialización de descriptores de memoria compartida para GPU/CPU."""
    desc = SharedBufferDescriptor(
        shm_name="gutoflow_shm_frame_raw_00123",
        width=8256,
        height=5504,
        stride_bytes=8256 * 3,
        pixel_format=PixelFormat.RGB8,
    )

    serialized = desc.serialize()
    assert len(serialized) == 80  # 64 bytes string + 16 bytes enteros

    deserialized = SharedBufferDescriptor.deserialize(serialized)
    assert deserialized.shm_name == "gutoflow_shm_frame_raw_00123"
    assert deserialized.width == 8256
    assert deserialized.height == 5504
    assert deserialized.stride_bytes == 8256 * 3
    assert deserialized.pixel_format == PixelFormat.RGB8

    # Validación de datos incompletos
    with pytest.raises(ValueError, match="Datos insuficientes"):
        SharedBufferDescriptor.deserialize(serialized[:50])


def test_shared_buffer_descriptor_unicode_name():
    """Valida nombres con caracteres acentuados o especiales sin fallos de decodificación."""
    desc = SharedBufferDescriptor(
        shm_name="búfer_sesión_niño_fotografía_rábano_001",
        width=1920,
        height=1080,
        stride_bytes=1920 * 4,
        pixel_format=PixelFormat.RGBA8,
    )
    serialized = desc.serialize()
    deserialized = SharedBufferDescriptor.deserialize(serialized)
    assert len(deserialized.shm_name) > 0
    assert deserialized.pixel_format == PixelFormat.RGBA8


def test_culling_verdict_payload_roundtrip():
    """Valida transporte de veredictos y puntajes de culling entre Python y Rust."""
    verdict = CullingVerdictPayload(
        frame_id=2048576,
        rating_stars=5,
        is_pick=True,
        is_rejected=False,
        eye_score=0.945,
        focus_sharpness_score=9.82,
        tilt_angle_deg=-2.34,
    )

    raw_bytes = verdict.serialize()
    decoded = CullingVerdictPayload.deserialize(raw_bytes)

    assert decoded.frame_id == 2048576
    assert decoded.rating_stars == 5
    assert decoded.is_pick is True
    assert decoded.is_rejected is False
    assert decoded.eye_score == pytest.approx(0.945, rel=1e-4)
    assert decoded.focus_sharpness_score == pytest.approx(9.82, rel=1e-4)
    assert decoded.tilt_angle_deg == pytest.approx(-2.34, rel=1e-4)


def test_full_message_lifecycle():
    """Valida empaquetado y decodificación extremo a extremo de un mensaje completo."""
    verdict = CullingVerdictPayload(
        frame_id=42,
        rating_stars=4,
        is_pick=False,
        is_rejected=False,
        eye_score=0.88,
        focus_sharpness_score=7.50,
        tilt_angle_deg=0.55,
    )
    payload_bytes = verdict.serialize()

    full_packet = LightCraftBridgeMessage.encode(
        msg_type=MessageType.CULLING_VERDICT_UPDATE,
        correlation_id=101,
        payload=payload_bytes,
    )

    msg_type, payload_len, corr_id = LightCraftBridgeMessage.decode_header(full_packet[:HEADER_SIZE])
    assert msg_type == MessageType.CULLING_VERDICT_UPDATE
    assert corr_id == 101

    extracted_payload = full_packet[HEADER_SIZE : HEADER_SIZE + payload_len]
    restored_verdict = CullingVerdictPayload.deserialize(extracted_payload)

    assert restored_verdict.frame_id == 42
    assert restored_verdict.rating_stars == 4
