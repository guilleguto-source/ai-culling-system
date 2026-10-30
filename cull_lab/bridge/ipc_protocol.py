"""
CullLab <-> LightCraft High-Performance IPC Protocol
Protocolo binario de baja latencia y memoria compartida (Zero-Copy)
Inspirado en la arquitectura IPC de Narrative Select (FlatBuffers/SharedMem)
y Photo Mechanic Plus (AVEventMachine).
"""

from __future__ import annotations

import enum
import struct
from dataclasses import dataclass
from typing import Optional, Tuple


MAGIC_BYTES = b"GTFL"  # GutoFlow Lightcraft Header Magic
PROTOCOL_VERSION = 1

# Estructura del Header de Mensaje (16 bytes):
# - 4s: Magic (b"GTFL")
# - H: Versión del protocolo (u16)
# - H: Tipo de mensaje (u16)
# - I: Longitud del payload (u32)
# - I: ID correlación / Frame Sequence (u32)
HEADER_FORMAT = "<4sHHII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class MessageType(enum.IntEnum):
    HEARTBEAT = 0x0001
    REGISTER_SHARED_BUFFER = 0x0002
    FRAME_READY_NOTIFICATION = 0x0003
    CULLING_VERDICT_UPDATE = 0x0004
    FOCUS_PEAKING_REQUEST = 0x0005
    RETOUCH_TASK_SUBMIT = 0x0006
    XMP_DELTA_SYNC = 0x0007
    ACK = 0x0008
    ERROR = 0x00FF


class PixelFormat(enum.IntEnum):
    RGB8 = 1
    RGBA8 = 2
    RAW_BAYER14 = 3
    LINEAR_DNG_F32 = 4


@dataclass
class SharedBufferDescriptor:
    """Descriptor para mapeo directo de memoria compartida GPU/CPU."""
    shm_name: str
    width: int
    height: int
    stride_bytes: int
    pixel_format: PixelFormat

    # Formato serializado del descriptor (64 bytes fijos para nombre + 4 enteros u32)
    # 64s: Nombre shm
    # 4I: width, height, stride, format
    DESCRIPTOR_FORMAT = "<64sIIII"

    def serialize(self) -> bytes:
        # Codificación segura preservando límites de caracteres UTF-8
        encoded = self.shm_name.encode("utf-8")
        if len(encoded) > 64:
            # Si excede 64 bytes, recortar cadena de forma limpia antes de re-codificar
            encoded = self.shm_name[:32].encode("utf-8")[:64]
        name_bytes = encoded.ljust(64, b"\x00")
        return struct.pack(
            self.DESCRIPTOR_FORMAT,
            name_bytes,
            self.width,
            self.height,
            self.stride_bytes,
            int(self.pixel_format),
        )

    @classmethod
    def deserialize(cls, data: bytes) -> SharedBufferDescriptor:
        desc_size = struct.calcsize(cls.DESCRIPTOR_FORMAT)
        if len(data) < desc_size:
            raise ValueError(f"Datos insuficientes para SharedBufferDescriptor: {len(data)} < {desc_size} bytes")

        name_bytes, width, height, stride, fmt = struct.unpack(cls.DESCRIPTOR_FORMAT, data[:desc_size])
        name = name_bytes.rstrip(b"\x00").decode("utf-8", errors="replace")
        return cls(
            shm_name=name,
            width=width,
            height=height,
            stride_bytes=stride,
            pixel_format=PixelFormat(fmt),
        )


@dataclass
class CullingVerdictPayload:
    """Metadatos de selección y foco calculados por GutoFlow enviados a LightCraft."""
    frame_id: int
    rating_stars: int
    is_pick: bool
    is_rejected: bool
    eye_score: float
    focus_sharpness_score: float
    tilt_angle_deg: float

    # Formato binario compacto:
    # Q: frame_id (u64)
    # B: rating_stars (u8)
    # ?: is_pick (bool)
    # ?: is_rejected (bool)
    # f: eye_score (f32)
    # f: focus_sharpness_score (f32)
    # f: tilt_angle_deg (f32)
    PAYLOAD_FORMAT = "<QB??fff"

    def serialize(self) -> bytes:
        return struct.pack(
            self.PAYLOAD_FORMAT,
            self.frame_id,
            self.rating_stars,
            self.is_pick,
            self.is_rejected,
            self.eye_score,
            self.focus_sharpness_score,
            self.tilt_angle_deg,
        )

    @classmethod
    def deserialize(cls, data: bytes) -> CullingVerdictPayload:
        payload_size = struct.calcsize(cls.PAYLOAD_FORMAT)
        if len(data) < payload_size:
            raise ValueError(f"Payload de veredicto incompleto: {len(data)} < {payload_size} bytes")

        frame_id, rating, is_pick, is_rej, eye, focus, tilt = struct.unpack(
            cls.PAYLOAD_FORMAT, data[:payload_size]
        )
        return cls(
            frame_id=frame_id,
            rating_stars=rating,
            is_pick=is_pick,
            is_rejected=is_rej,
            eye_score=eye,
            focus_sharpness_score=focus,
            tilt_angle_deg=tilt,
        )


class LightCraftBridgeMessage:
    """Constructor y deserializador del protocolo binario de transporte GTFL."""

    @staticmethod
    def encode(msg_type: MessageType, correlation_id: int, payload: bytes) -> bytes:
        """Empaqueta un mensaje binario con su header."""
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            PROTOCOL_VERSION,
            int(msg_type),
            len(payload),
            correlation_id,
        )
        return header + payload

    @staticmethod
    def decode_header(header_bytes: bytes) -> Tuple[MessageType, int, int]:
        """
        Decodifica y valida el header binario de 16 bytes.
        Retorna: (msg_type, payload_length, correlation_id).
        Lanza ValueError si el magic o la versión son inválidos.
        """
        if len(header_bytes) < HEADER_SIZE:
            raise ValueError(f"Header incompleto: esperado {HEADER_SIZE} bytes, recibido {len(header_bytes)}")

        magic, version, raw_type, payload_len, corr_id = struct.unpack(HEADER_FORMAT, header_bytes[:HEADER_SIZE])
        if magic != MAGIC_BYTES:
            raise ValueError(f"Magic bytes inválidos: {magic!r}")
        if version != PROTOCOL_VERSION:
            raise ValueError(f"Versión de protocolo no soportada: {version}")

        return MessageType(raw_type), payload_len, corr_id
