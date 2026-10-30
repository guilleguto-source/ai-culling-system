"""
Pruebas automatizadas de resistencia e integridad para XmpExporter y XmpDeltaAccumulator.
"""

import concurrent.futures
import shutil
import tempfile
import time
from pathlib import Path

from cull_lab.core.xmp_exporter import MetadataDelta, XmpDeltaAccumulator, XmpExporter


def test_create_and_read_new_xmp():
    """Valida la creación atómica de un XMP limpio y su lectura correcta."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_raw = Path(tmpdir) / "DSC01920.ARW"
        xmp_path = XmpExporter.get_xmp_path(fake_raw)

        delta = MetadataDelta(
            rating=5,
            label="Green",
            pick_status=1,
            crop_angle=2.3456,
            has_crop=True,
            exposure_2012=0.65,
        )

        res_path = XmpExporter.apply_delta(xmp_path, delta)
        assert res_path.exists()
        assert res_path == xmp_path

        # Leer de vuelta
        meta = XmpExporter.read_metadata(xmp_path)
        assert meta["rating"] == 5
        assert meta["label"] == "Green"
        assert meta["pick"] == 1
        assert abs(meta["crop_angle"] - 2.3456) < 1e-3
        assert meta["has_crop"] is True
        assert abs(meta["exposure_2012"] - 0.65) < 1e-2


def test_merge_preserves_unmodified_metadata():
    """Valida que un delta parcial conserve metadatos existentes sin borrarlos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xmp_path = Path(tmpdir) / "IMG_4001.xmp"

        # 1. Escritura inicial
        initial_delta = MetadataDelta(
            rating=3,
            label="Yellow",
            crop_angle=-1.20,
            has_crop=True,
        )
        XmpExporter.apply_delta(xmp_path, initial_delta)

        # 2. Delta parcial (solo cambia calificación a 5 y agrega exposición)
        second_delta = MetadataDelta(
            rating=5,
            exposure_2012=-0.35,
        )
        XmpExporter.apply_delta(xmp_path, second_delta)

        # 3. Verificar que label y crop_angle originales sigan intactos
        meta = XmpExporter.read_metadata(xmp_path)
        assert meta["rating"] == 5
        assert meta["label"] == "Yellow"  # Conservado
        assert abs(meta["crop_angle"] - (-1.20)) < 1e-2  # Conservado
        assert abs(meta["exposure_2012"] - (-0.35)) < 1e-2


def test_concurrent_atomic_writes():
    """Valida la robustez y ausencia de bloqueos o archivos corruptos bajo alta concurrencia."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xmp_path = Path(tmpdir) / "CONCURRENT_TEST.xmp"

        def worker(rating_val: int):
            delta = MetadataDelta(
                rating=rating_val,
                label=f"Label_{rating_val}",
            )
            XmpExporter.apply_delta(xmp_path, delta)

        # Lanzar 30 escrituras concurrentes sobre el mismo archivo
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i % 6) for i in range(30)]
            for f in concurrent.futures.as_completed(futures):
                f.result()  # Comprueba que no se lancen excepciones

        assert xmp_path.exists()
        meta = XmpExporter.read_metadata(xmp_path)
        assert 0 <= meta["rating"] <= 5
        assert meta["label"].startswith("Label_")


def test_accumulator_batch_flushing():
    """Valida la consolidación en memoria del acumulador con debounce antes de persistir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = Path(tmpdir) / "BURST_001.CR3"
        xmp_path = XmpExporter.get_xmp_path(raw_path)

        accum = XmpDeltaAccumulator(debounce_seconds=0.1)

        try:
            # Simular 10 pulsaciones rápidas de teclas en 50 ms
            for r in range(1, 6):
                accum.record_delta(raw_path, MetadataDelta(rating=r))
                time.sleep(0.01)

            # En este punto el archivo aún no debe existir o solo tener valor parcial
            # Forzamos flush
            accum.flush_sync()

            assert xmp_path.exists()
            meta = XmpExporter.read_metadata(xmp_path)
            assert meta["rating"] == 5  # El último valor consolidado

        finally:
            accum.shutdown()


if __name__ == "__main__":
    print("Ejecutando pruebas unitarias de XmpExporter...")
    test_create_and_read_new_xmp()
    print("  ✓ test_create_and_read_new_xmp OK")
    test_merge_preserves_unmodified_metadata()
    print("  ✓ test_merge_preserves_unmodified_metadata OK")
    test_concurrent_atomic_writes()
    print("  ✓ test_concurrent_atomic_writes OK")
    test_accumulator_batch_flushing()
    print("  ✓ test_accumulator_batch_flushing OK")
    print("¡Todas las pruebas pasaron exitosamente!")
