"""
process_nas_sessions.py — Procesador masivo en lote de producción para GutoFlow + GutoCraft.
Procesa sesiones completas en red (NAS \\MYCLOUDEX2ULTRA):
  1. Genera los 5 planos alpha neuronales (Sujeto, Piel, Esclera, Iris, Dientes).
  2. Pre-calcula el cache nativo de GutoCraft (512x512 u8 .bin).
  3. Escribe los sidecars .xmp compatibles con Adobe Lightroom y LightCraft
     con metadatos de curaduría y crs:MaskGroupBasedCorrections.
"""
import sys
import os
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from lxml import etree

from services.mask_generator import generate_all_masks, load_image
from services.app_paths import get_models_dir

SESSIONS = {
    "giler": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler"),
    "dayana": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Dayana"),
    "gioconda": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Gioconda"),
}

CACHE_DIR = get_models_dir() / "cache" / "mattes"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".cr2", ".cr3", ".nef", ".arw", ".dng"}


def photo_cache_key(path_str: str) -> str:
    """Calcula el hash fnv1a idéntico a LightCraft media.rs::photo_cache_key."""
    h = 0xcbf29ce484222325
    for b in path_str.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return f"{h:016x}"


def generate_lightroom_xmp(image_path: Path, xmp_path: Path, auto_exp: float = 0.0):
    """Genera sidecar XMP con ajustes de revelado y crs:MaskGroupBasedCorrections para Lightroom/LightCraft."""
    NS_X = "adobe:ns:meta/"
    NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    NS_CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"

    xmpmeta = etree.Element(f"{{{NS_X}}}xmpmeta", nsmap={"x": NS_X})
    xmpmeta.set(f"{{{NS_X}}}xmptk", "GutoFlow + GutoCraft 2.0")
    rdf = etree.SubElement(xmpmeta, f"{{{NS_RDF}}}RDF", nsmap={"rdf": NS_RDF})
    desc = etree.SubElement(
        rdf, f"{{{NS_RDF}}}Description",
        nsmap={"rdf": NS_RDF, "crs": NS_CRS}
    )
    desc.set(f"{{{NS_RDF}}}about", "")

    # Ajustes globales
    desc.set(f"{{{NS_CRS}}}Version", "16.0")
    desc.set(f"{{{NS_CRS}}}ProcessVersion", "15.4")
    desc.set(f"{{{NS_CRS}}}Exposure2012", f"{auto_exp:+.2f}")
    desc.set(f"{{{NS_CRS}}}Contrast2012", "+10")
    desc.set(f"{{{NS_CRS}}}Highlights2012", "-18")
    desc.set(f"{{{NS_CRS}}}Shadows2012", "+20")
    desc.set(f"{{{NS_CRS}}}Whites2012", "+8")
    desc.set(f"{{{NS_CRS}}}Blacks2012", "-8")
    desc.set(f"{{{NS_CRS}}}Texture", "0")
    desc.set(f"{{{NS_CRS}}}Clarity2012", "+5")
    desc.set(f"{{{NS_CRS}}}Vibrance", "+8")
    desc.set(f"{{{NS_CRS}}}Saturation", "0")

    # Contenedor de Máscaras IA (crs:MaskGroupBasedCorrections)
    corrections = etree.SubElement(desc, f"{{{NS_CRS}}}MaskGroupBasedCorrections")
    seq = etree.SubElement(corrections, f"{{{NS_RDF}}}Seq")

    # Definición de las 5 capas anatómicas y sujeto
    mask_definitions = [
        # (Nombre, SubType, SubCatID, Sliders dict)
        ("Sujeto Pop (GutoCraft)", "1", None, {
            "LocalExposure2012": "+0.0625", # +0.25 EV
            "LocalContrast2012": "+0.10",
        }),
        ("Piel Facial (GutoCraft)", "3", "2", {
            "LocalTexture": "-0.16",
            "LocalClarity2012": "-0.08",
        }),
        ("Esclera Ojos (GutoCraft)", "3", "8", {
            "LocalSaturation": "-0.22",
        }),
        ("Iris y Pupila (GutoCraft)", "3", "3", {
            "LocalExposure2012": "+0.0875", # +0.35 EV
            "LocalClarity2012": "+0.15",
        }),
        ("Dientes (GutoCraft)", "3", "12", {
            "LocalSaturation": "-0.25",
            "LocalExposure2012": "+0.0625",
        }),
    ]

    for name, sub_type, sub_cat, sliders in mask_definitions:
        li = etree.SubElement(seq, f"{{{NS_RDF}}}li")
        li.set(f"{{{NS_CRS}}}What", "Correction")
        li.set(f"{{{NS_CRS}}}CorrectionAmount", "1.000000")
        li.set(f"{{{NS_CRS}}}CorrectionActive", "true")
        li.set(f"{{{NS_CRS}}}CorrectionName", name)
        li.set(f"{{{NS_CRS}}}CorrectionSyncID", photo_cache_key(name))

        for k, v in sliders.items():
            li.set(f"{{{NS_CRS}}}{k}", v)

        # Componente Mask/Image
        mask_list = etree.SubElement(li, f"{{{NS_CRS}}}CorrectionMasks")
        mask_seq = etree.SubElement(mask_list, f"{{{NS_RDF}}}Seq")
        m_li = etree.SubElement(mask_seq, f"{{{NS_RDF}}}li")
        m_li.set(f"{{{NS_CRS}}}What", "Mask/Image")
        m_li.set(f"{{{NS_CRS}}}MaskActive", "true")
        m_li.set(f"{{{NS_CRS}}}MaskName", name)
        m_li.set(f"{{{NS_CRS}}}MaskBlendMode", "0")
        m_li.set(f"{{{NS_CRS}}}MaskInverted", "false")
        m_li.set(f"{{{NS_CRS}}}MaskSubType", sub_type)
        if sub_cat is not None:
            m_li.set(f"{{{NS_CRS}}}MaskSubCategoryID", sub_cat)

    xml_bytes = etree.tostring(xmpmeta, encoding="utf-8", pretty_print=True)
    packet = b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' + xml_bytes + b'\n<?xpacket end="w"?>'

    with open(xmp_path, "wb") as f:
        f.write(packet)


def process_single_photo(photo_path: Path):
    """Procesa una sola foto: máscaras IA en cache y sidecar XMP."""
    try:
        xmp_path = photo_path.with_suffix(".xmp")
        key = photo_cache_key(str(photo_path))
        target_cache_dir = CACHE_DIR / key

        # 1. Generar máscaras IA si no están ya en cache
        bin_files = ["person.bin", "facial_skin.bin", "eye_sclera.bin", "iris_pupil.bin", "teeth.bin"]
        all_cached = all((target_cache_dir / b).exists() for b in bin_files)

        if xmp_path.exists() and all_cached:
            return True, photo_path.name, None

        if not all_cached:
            generate_all_masks(str(photo_path), str(target_cache_dir))

        # 2. Generar sidecar .xmp
        generate_lightroom_xmp(photo_path, xmp_path, auto_exp=0.0)

        return True, photo_path.name, None
    except Exception as e:
        return False, photo_path.name, str(e)


def process_folder(folder_path: Path, max_workers: int = 4):
    """Procesa recursivamente todas las fotos de una carpeta."""
    if not folder_path.exists():
        print(f"[!] Carpeta no encontrada: {folder_path}")
        return

    photos = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    photos.sort(key=lambda p: p.name)

    total = len(photos)
    print(f"\n=======================================================")
    print(f" PROCESANDO SESIÓN: {folder_path.name}")
    print(f" Total fotos a revelar: {total}")
    print(f" Destino máscaras: {CACHE_DIR}")
    print(f"=======================================================")

    t0 = time.time()
    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_photo = {executor.submit(process_single_photo, p): p for p in photos}
        done_count = 0

        for future in as_completed(future_to_photo):
            done_count += 1
            ok, name, err = future.result()
            if ok:
                success_count += 1
            else:
                fail_count += 1
                sys.stderr.write(f"\n[!] Error en {name}: {err}\n")

            if done_count % 10 == 0 or done_count == total:
                elapsed = time.time() - t0
                fps = done_count / max(0.1, elapsed)
                rem_sec = (total - done_count) / max(0.1, fps)
                pct = (done_count / total) * 100
                print(f"  [{pct:5.1f}%] {done_count}/{total} fotos | {fps:.2f} fotos/s | ETA: {rem_sec/60:.1f} min")

    total_time = time.time() - t0
    print(f"\n[OK] Sesión '{folder_path.name}' completada en {total_time/60:.2f} min ({success_count} procesadas, {fail_count} errores).")


def main():
    parser = argparse.ArgumentParser(description="Procesador masivo NAS para GutoFlow + GutoCraft")
    parser.add_argument("--session", choices=["giler", "dayana", "gioconda", "all"], default="all",
                        help="Sesión a procesar (giler, dayana, gioconda o all)")
    parser.add_argument("--workers", type=int, default=3, help="Hilos paralelos")
    args = parser.parse_args()

    if args.session == "all":
        sessions_to_run = ["giler", "dayana", "gioconda"]
    else:
        sessions_to_run = [args.session]

    for s_name in sessions_to_run:
        process_folder(SESSIONS[s_name], max_workers=args.workers)


if __name__ == "__main__":
    main()
