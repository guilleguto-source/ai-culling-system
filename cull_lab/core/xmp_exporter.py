"""
CullLab XMP & Sidecar Exporter
Inspirado en el acumulador asíncrono de Photo Mechanic (AVNRFMetadataDiffsAccumulator)
y los esquemas de Adobe Camera Raw (crs) y Capture One (cos).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("cull_lab.xmp_exporter")

# Namespaces estándar
NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "crs": "http://ns.adobe.com/camera-raw-settings/1.0/",
    "lr": "http://ns.adobe.com/lightroom/1.0/",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


@dataclass
class MetadataDelta:
    """Representa un delta de modificación sobre metadatos."""
    rating: Optional[int] = None                  # 0 a 5 estrellas
    label: Optional[str] = None                   # Red, Yellow, Green, Blue, Purple
    pick_status: Optional[int] = None             # 1 (Pick), 0 (Unflagged), -1 (Reject)
    crop_angle: Optional[float] = None            # Ángulo de nivelación (grados)
    has_crop: Optional[bool] = None               # Flag de recorte activo
    crop_coords: Optional[tuple[float, float, float, float]] = None # (Top, Left, Bottom, Right) en [0, 1]
    exposure_2012: Optional[float] = None         # Ajuste EV (-5.0 a +5.0)
    extra_crs: Dict[str, Any] = field(default_factory=dict)


class XmpExporter:
    """
    Generador y sincronizador atómico de archivos sidecar XMP.
    Garantiza cero corrupción ante caídas o concurrencia multihilo.
    """

    @staticmethod
    def get_xmp_path(image_path: str | Path) -> Path:
        """Calcula la ruta del sidecar .xmp correspondiente."""
        p = Path(image_path)
        return p.with_suffix(".xmp")

    _locks_mutex = threading.Lock()
    _active_file_locks: Dict[Path, threading.Lock] = {}

    @classmethod
    def _get_file_lock(cls, path: Path) -> threading.Lock:
        resolved = path.resolve()
        with cls._locks_mutex:
            if resolved not in cls._active_file_locks:
                cls._active_file_locks[resolved] = threading.Lock()
            return cls._active_file_locks[resolved]

    @classmethod
    def apply_delta(cls, xmp_path: str | Path, delta: MetadataDelta) -> Path:
        """
        Aplica un delta de metadatos de forma atómica sobre el archivo XMP.
        Si el archivo ya existe, actualiza los nodos sin borrar otros metadatos.
        Si no existe, crea un contenedor XMP válido y ligero.
        """
        target_path = Path(xmp_path)
        file_lock = cls._get_file_lock(target_path)

        with file_lock:
            temp_path = target_path.with_name(f"{target_path.name}.tmp.{uuid.uuid4().hex}")
            try:
                # 1. Leer existente o crear nuevo árbol
                if target_path.exists() and target_path.stat().st_size > 0:
                    root = cls._parse_existing_xmp(target_path)
                else:
                    root = cls._create_blank_xmp()

                # 2. Localizar o crear el elemento rdf:Description
                desc = cls._get_or_create_description(root)

                # 3. Aplicar campos del delta
                if delta.rating is not None:
                    rating_val = max(0, min(5, int(delta.rating)))
                    desc.set(f"{{{NS['xmp']}}}Rating", str(rating_val))

                if delta.label is not None:
                    desc.set(f"{{{NS['xmp']}}}Label", str(delta.label))

                if delta.pick_status is not None:
                    # Lightroom y Capture One pick flag
                    pick_val = 1 if delta.pick_status > 0 else (-1 if delta.pick_status < 0 else 0)
                    desc.set(f"{{{NS['crs']}}}Pick", str(pick_val))
                    if pick_val != 0:
                        desc.set(f"{{{NS['photoshop']}}}Urgency", str(pick_val))

                if delta.crop_angle is not None:
                    desc.set(f"{{{NS['crs']}}}CropAngle", f"{delta.crop_angle:.4f}")
                    desc.set(f"{{{NS['crs']}}}HasCrop", "True")

                if delta.has_crop is not None:
                    desc.set(f"{{{NS['crs']}}}HasCrop", "True" if delta.has_crop else "False")

                if delta.crop_coords is not None:
                    top, left, bottom, right = delta.crop_coords
                    desc.set(f"{{{NS['crs']}}}CropTop", f"{top:.6f}")
                    desc.set(f"{{{NS['crs']}}}CropLeft", f"{left:.6f}")
                    desc.set(f"{{{NS['crs']}}}CropBottom", f"{bottom:.6f}")
                    desc.set(f"{{{NS['crs']}}}CropRight", f"{right:.6f}")
                    desc.set(f"{{{NS['crs']}}}HasCrop", "True")

                if delta.exposure_2012 is not None:
                    desc.set(f"{{{NS['crs']}}}Exposure2012", f"{delta.exposure_2012:+.2f}")

                for k, v in delta.extra_crs.items():
                    desc.set(f"{{{NS['crs']}}}{k}", str(v))

                # 4. Serializar en archivo temporal
                xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=False).decode("utf-8")
                packet = cls._wrap_xpacket(xml_str)

                with open(temp_path, "wb") as f:
                    f.write(packet.encode("utf-8"))
                    f.flush()
                    os.fsync(f.fileno())

                # 5. Swap atómico con tolerancia a bloqueos transitorios en Windows
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        os.replace(temp_path, target_path)
                        break
                    except (PermissionError, OSError) as e:
                        if attempt == max_retries - 1:
                            raise
                        time.sleep(0.01 * (attempt + 1))

                return target_path

            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.debug("No se pudo eliminar archivo temporal %s: %s", temp_path, e)

    @classmethod
    def read_metadata(cls, xmp_path: str | Path) -> Dict[str, Any]:
        """Lee y normaliza los metadatos esenciales de un archivo XMP."""
        target_path = Path(xmp_path)
        if not target_path.exists():
            return {}

        root = cls._parse_existing_xmp(target_path)
        desc = cls._get_or_create_description(root)

        meta: Dict[str, Any] = {}
        rating = desc.get(f"{{{NS['xmp']}}}Rating")
        if rating is not None:
            try:
                meta["rating"] = int(rating)
            except ValueError:
                pass

        label = desc.get(f"{{{NS['xmp']}}}Label")
        if label is not None:
            meta["label"] = label

        pick = desc.get(f"{{{NS['crs']}}}Pick")
        if pick is not None:
            try:
                meta["pick"] = int(pick)
            except ValueError:
                pass

        crop_angle = desc.get(f"{{{NS['crs']}}}CropAngle")
        if crop_angle is not None:
            try:
                meta["crop_angle"] = float(crop_angle)
            except ValueError:
                pass

        has_crop = desc.get(f"{{{NS['crs']}}}HasCrop")
        if has_crop is not None:
            meta["has_crop"] = has_crop.lower() == "true"

        exposure = desc.get(f"{{{NS['crs']}}}Exposure2012")
        if exposure is not None:
            try:
                meta["exposure_2012"] = float(exposure)
            except ValueError:
                pass

        return meta

    # --- Métodos Internos de Construcción XML ---

    @staticmethod
    def _create_blank_xmp() -> ET.Element:
        root = ET.Element(f"{{{NS['x']}}}xmpmeta")
        root.set(f"{{{NS['x']}}}xmptk", "GutoFlow XMP Engine 1.0")
        rdf = ET.SubElement(root, f"{{{NS['rdf']}}}RDF")
        desc = ET.SubElement(rdf, f"{{{NS['rdf']}}}Description")
        desc.set(f"{{{NS['rdf']}}}about", "")
        return root

    @staticmethod
    def _parse_existing_xmp(path: Path) -> ET.Element:
        with open(path, "rb") as f:
            raw = f.read()

        # Limpiar cabeceras de paquete xpacket para parsing estricto XML
        text = raw.decode("utf-8", errors="ignore")
        start = text.find("<x:xmpmeta")
        end = text.find("</x:xmpmeta>")
        if start != -1 and end != -1:
            xml_snippet = text[start : end + len("</x:xmpmeta>")]
            return ET.fromstring(xml_snippet)

        # Fallback a parseo directo
        return ET.parse(path).getroot()

    @staticmethod
    def _get_or_create_description(root: ET.Element) -> ET.Element:
        rdf = root.find(f"{{{NS['rdf']}}}RDF")
        if rdf is None:
            rdf = ET.SubElement(root, f"{{{NS['rdf']}}}RDF")
        desc = rdf.find(f"{{{NS['rdf']}}}Description")
        if desc is None:
            desc = ET.SubElement(rdf, f"{{{NS['rdf']}}}Description")
            desc.set(f"{{{NS['rdf']}}}about", "")
        return desc

    @staticmethod
    def _wrap_xpacket(xml_str: str) -> str:
        return (
            '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            f"{xml_str}\n"
            '<?xpacket end="w"?>\n'
        )


class XmpDeltaAccumulator:
    """
    Acumulador en memoria inspirado en Photo Mechanic (AVNRFMetadataDiffsAccumulator).
    Soporta escrituras concurrentes ultrarrápidas, consolidando múltiples
    cambios antes de escribirlos en disco para evitar congestión de I/O.
    """

    def __init__(self, debounce_seconds: float = 0.05):
        self._debounce = debounce_seconds
        self._lock = threading.Lock()
        self._pending: Dict[Path, MetadataDelta] = {}
        self._last_update: Dict[Path, float] = {}
        self.failed_flushes: List[Tuple[Path, str]] = []
        self._running = True
        self._worker_thread = threading.Thread(target=self._flusher_loop, daemon=True)
        self._worker_thread.start()

    def record_delta(self, image_or_xmp_path: str | Path, delta: MetadataDelta) -> None:
        """Registra o fusiona un cambio de metadatos en memoria de forma instantánea (< 10 µs)."""
        p = Path(image_or_xmp_path)
        xmp_path = p if p.suffix.lower() == ".xmp" else p.with_suffix(".xmp")

        with self._lock:
            existing = self._pending.get(xmp_path)
            if existing is None:
                self._pending[xmp_path] = delta
            else:
                # Merge no destructivo de deltas
                if delta.rating is not None:
                    existing.rating = delta.rating
                if delta.label is not None:
                    existing.label = delta.label
                if delta.pick_status is not None:
                    existing.pick_status = delta.pick_status
                if delta.crop_angle is not None:
                    existing.crop_angle = delta.crop_angle
                if delta.has_crop is not None:
                    existing.has_crop = delta.has_crop
                if delta.crop_coords is not None:
                    existing.crop_coords = delta.crop_coords
                if delta.exposure_2012 is not None:
                    existing.exposure_2012 = delta.exposure_2012
                existing.extra_crs.update(delta.extra_crs)

            self._last_update[xmp_path] = time.time()

    def flush_sync(self, xmp_path: Optional[str | Path] = None) -> None:
        """Fuerza la persistencia síncrona inmediata en disco."""
        targets: Dict[Path, MetadataDelta] = {}
        with self._lock:
            if xmp_path is not None:
                p = Path(xmp_path)
                xp = p if p.suffix.lower() == ".xmp" else p.with_suffix(".xmp")
                if xp in self._pending:
                    targets[xp] = self._pending.pop(xp)
                    self._last_update.pop(xp, None)
            else:
                targets = dict(self._pending)
                self._pending.clear()
                self._last_update.clear()

        for xp, delta in targets.items():
            try:
                XmpExporter.apply_delta(xp, delta)
            except Exception as e:
                logger.error("Error en flush_sync para %s: %s", xp, e, exc_info=True)
                self.failed_flushes.append((xp, str(e)))

    def _flusher_loop(self) -> None:
        """Hilo de fondo que procesa deltas cuyo debounce haya expirado."""
        while self._running:
            time.sleep(self._debounce / 2)
            now = time.time()
            to_flush: Dict[Path, MetadataDelta] = {}

            with self._lock:
                ready_keys: Set[Path] = set()
                for path, last_time in self._last_update.items():
                    if now - last_time >= self._debounce:
                        ready_keys.add(path)

                for k in ready_keys:
                    to_flush[k] = self._pending.pop(k)
                    del self._last_update[k]

            for xp, delta in to_flush.items():
                try:
                    XmpExporter.apply_delta(xp, delta)
                except Exception as e:
                    logger.error("Error persistiendo delta XMP para %s: %s", xp, e, exc_info=True)
                    self.failed_flushes.append((xp, str(e)))

    def shutdown(self) -> None:
        """Detiene el hilo y descarga todos los deltas pendientes."""
        self._running = False
        self.flush_sync()
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
