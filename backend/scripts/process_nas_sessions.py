"""
process_nas_sessions.py — Procesador masivo en lote de producción para GutoFlow + GutoCraft.
Procesa sesiones completas en red (NAS \\MYCLOUDEX2ULTRA):
  1. Genera los 5 planos alpha neuronales (Sujeto Pop, Piel, Esclera, Iris, Dientes).
     - Segmentación híbrida tiled para cuerpo completo en fotos grupales (YOLOv8 + Selfie Segmenter).
  2. Culling jerárquico centrado en VIPs:
     - Detección de identidades ArcFace y selección de protagonistas.
     - Evaluación de contacto visual (gaze_score) y apertura palpebral (EAR).
     - Regla condicional para niños de 2 a 5 años (vip_smile_relaxed si sonrisa < 20%).
     - Inmunidad de secundarios ante parpadeos.
  3. Pre-calcula el cache nativo de GutoCraft (512x512 u8 .bin).
  4. Escribe los sidecars .xmp compatibles con Adobe Lightroom y LightCraft
     con metadatos de curaduría (Rating, Label, Pick) y crs:MaskGroupBasedCorrections.
"""
import sys
import os
import io
import gc
import time
import json
from typing import Optional, List, Dict, Tuple
import argparse
import threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image, ExifTags
from lxml import etree

from services.mask_generator import (
    generate_all_masks, load_image, nms_boxes,
    YUNET_PATH, LANDMARKER_PATH, SEGMENTER_PATH
)
from services.face_assessment import compute_face_sharpness, compute_biometric_face_attributes
from services.legacy.face_identity import embed_face
from services.face_identity import group_event_identities, rank_vip_identities
from services.cluster_gates import apply_technical_gates_explained
from services.app_paths import get_models_dir
from services.ingester import _compute_phash
from services.rust_bridge import get_burst_id
from services.thumbnail_store import save_thumbnail_to_disk
from services.decision import photos_for_group_coverage

SESSIONS = {
    "giler": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler"),
    "dayana": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Dayana"),
    "gioconda": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Gioconda"),
    "luciana": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Luciana"),
}

CACHE_DIR = get_models_dir() / "cache" / "mattes"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".cr2", ".cr3", ".nef", ".arw", ".dng"}

_thread_local = threading.local()


def photo_cache_key(path_str: str) -> str:
    """Calcula el hash fnv1a idéntico a LightCraft media.rs::photo_cache_key."""
    normalized = path_str.replace("\\", "/").lower()
    h = 0xcbf29ce484222325
    for b in normalized.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return f"{h:016x}"


def get_thread_yunet(w: int, h: int):
    """Obtiene o inicializa el detector YuNet para el hilo actual."""
    if not hasattr(_thread_local, "yunet") or _thread_local.yunet is None:
        if YUNET_PATH.exists():
            _thread_local.yunet = cv2.FaceDetectorYN.create(
                str(YUNET_PATH), "", (w, h),
                score_threshold=0.55, nms_threshold=0.30
            )
        else:
            _thread_local.yunet = None
    else:
        _thread_local.yunet.setInputSize((w, h))
    return _thread_local.yunet


def get_thread_landmarker():
    """Obtiene o inicializa MediaPipe FaceLandmarker para el hilo actual."""
    if not hasattr(_thread_local, "landmarker") or _thread_local.landmarker is None:
        if LANDMARKER_PATH.exists():
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision
                base_opts = mp_python.BaseOptions(model_asset_path=str(LANDMARKER_PATH))
                opts = vision.FaceLandmarkerOptions(base_options=base_opts, num_faces=1)
                _thread_local.landmarker = vision.FaceLandmarker.create_from_options(opts)
            except Exception:
                _thread_local.landmarker = None
        else:
            _thread_local.landmarker = None
    return _thread_local.landmarker


def get_exif_time(path: Path) -> tuple[float, str]:
    """Extrae la fecha y hora de captura original del archivo."""
    try:
        with Image.open(path) as img:
            exif = img._getexif()
            if exif:
                for tag, val in exif.items():
                    name = ExifTags.TAGS.get(tag)
                    if name in ("DateTimeOriginal", "DateTime"):
                        dt_str = str(val).strip()
                        dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                        return dt.timestamp(), dt_str
    except Exception:
        pass

    try:
        import exifread
        with open(path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="DateTimeOriginal", details=False)
            if "EXIF DateTimeOriginal" in tags:
                dt_str = str(tags["EXIF DateTimeOriginal"]).strip()
                dt = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                return dt.timestamp(), dt_str
    except Exception:
        pass

    # Fallback: mtime del archivo
    mtime = os.path.getmtime(path)
    dt_str = datetime.fromtimestamp(mtime).strftime("%Y:%m:%d %H:%M:%S")
    return mtime, dt_str


def generate_lightroom_xmp(
    image_path: Path,
    xmp_path: Path,
    auto_exp: float = 0.0,
    rating: int = 0,
    label: str = "",
    pick: str = "0",
    face_regions: Optional[List[Dict[str, float]]] = None,
    image_dims: Optional[Tuple[int, int]] = None,
):
    """
    Genera sidecar XMP compatible con Lightroom Classic, Bridge y LightCraft
    con metadatos de curaduría y crs:MaskGroupBasedCorrections.
    """
    NS_X = "adobe:ns:meta/"
    NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    NS_XMP = "http://ns.adobe.com/xap/1.0/"
    NS_CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"

    xmpmeta = etree.Element(f"{{{NS_X}}}xmpmeta", nsmap={"x": NS_X})
    xmpmeta.set(f"{{{NS_X}}}xmptk", "GutoFlow + GutoCraft 2.0")
    rdf = etree.SubElement(xmpmeta, f"{{{NS_RDF}}}RDF", nsmap={"rdf": NS_RDF})
    NS_MWG_RS = "http://www.metadataworkinggroup.com/schemas/regions/"
    NS_ST_AREA = "http://ns.adobe.com/xmp/sType/Area#"
    NS_ST_DIM = "http://ns.adobe.com/xap/1.0/sType/Dimensions#"

    desc = etree.SubElement(
        rdf, f"{{{NS_RDF}}}Description",
        nsmap={
            "rdf": NS_RDF,
            "crs": NS_CRS,
            "xmp": NS_XMP,
            "mwg-rs": NS_MWG_RS,
            "stArea": NS_ST_AREA,
            "stDim": NS_ST_DIM,
        }
    )
    desc.set(f"{{{NS_RDF}}}about", "")

    # Curaduría / Culling (Lightroom Classic, Bridge & LightCraft)
    rating_el = etree.SubElement(desc, f"{{{NS_XMP}}}Rating")
    rating_el.text = str(rating)
    label_el = etree.SubElement(desc, f"{{{NS_XMP}}}Label")
    label_el.text = label
    xmp_pick_el = etree.SubElement(desc, f"{{{NS_XMP}}}Pick")
    xmp_pick_el.text = str(pick)
    crs_pick_el = etree.SubElement(desc, f"{{{NS_CRS}}}Pick")
    crs_pick_el.text = str(pick)

    # Atributos directos en rdf:Description para máxima compatibilidad
    desc.set(f"{{{NS_XMP}}}Rating", str(rating))
    desc.set(f"{{{NS_XMP}}}Label", label)
    desc.set(f"{{{NS_XMP}}}Pick", str(pick))
    desc.set(f"{{{NS_CRS}}}Pick", str(pick))

    # Ajustes globales de revelado
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

    mask_definitions = [
        ("Sujeto Pop (GutoCraft)", "1", None, {
            "LocalExposure2012": "+0.0625",
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
            "LocalExposure2012": "+0.0875",
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

    # mwg-rs:Regions para que LightCraft sintetice las máscaras en <1ms
    if face_regions:
        w_px, h_px = image_dims if image_dims else (4000, 3000)
        regions_el = etree.SubElement(desc, f"{{{NS_MWG_RS}}}Regions")
        regions_el.set(f"{{{NS_RDF}}}parseType", "Resource")

        app_dim = etree.SubElement(regions_el, f"{{{NS_MWG_RS}}}AppliedToDimensions")
        app_dim.set(f"{{{NS_RDF}}}parseType", "Resource")
        app_dim.set(f"{{{NS_ST_DIM}}}w", str(w_px))
        app_dim.set(f"{{{NS_ST_DIM}}}h", str(h_px))
        app_dim.set(f"{{{NS_ST_DIM}}}unit", "pixel")

        reg_list = etree.SubElement(regions_el, f"{{{NS_MWG_RS}}}RegionList")
        bag = etree.SubElement(reg_list, f"{{{NS_RDF}}}Bag")
        for r in face_regions:
            li = etree.SubElement(bag, f"{{{NS_RDF}}}li")
            li.set(f"{{{NS_RDF}}}parseType", "Resource")
            area = etree.SubElement(li, f"{{{NS_MWG_RS}}}Area")
            area.set(f"{{{NS_RDF}}}parseType", "Resource")
            area.set(f"{{{NS_ST_AREA}}}x", f"{r['x']:.6f}")
            area.set(f"{{{NS_ST_AREA}}}y", f"{r['y']:.6f}")
            area.set(f"{{{NS_ST_AREA}}}w", f"{r['w']:.6f}")
            area.set(f"{{{NS_ST_AREA}}}h", f"{r['h']:.6f}")
            area.set(f"{{{NS_ST_AREA}}}unit", "normalized")
            type_el = etree.SubElement(li, f"{{{NS_MWG_RS}}}Type")
            type_el.text = "Face"

    xml_bytes = etree.tostring(xmpmeta, encoding="utf-8", pretty_print=True)
    packet = b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' + xml_bytes + b'\n<?xpacket end="w"?>'

    # Escritura atómica para red/NAS
    tmp_path = xmp_path.with_name(f"{xmp_path.stem}_{os.getpid()}_{int(time.time()*1000)}.xmp.tmp")
    with open(tmp_path, "wb") as f:
        f.write(packet)
    tmp_path.replace(xmp_path)


def analyze_or_load_photo(photo_path: Path, force: bool = False) -> dict:
    """Analiza una foto o carga su metadata y máscaras desde el cache."""
    key = photo_cache_key(str(photo_path))
    target_cache_dir = CACHE_DIR / key
    meta_path = target_cache_dir / "meta.json"
    bin_p = target_cache_dir / "person.bin"

    # Verificar si ya existe metadata serializada (solo si no es force y máscaras son proporcionales)
    if not force and meta_path.exists() and bin_p.exists() and bin_p.stat().st_size != 512 * 512:
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Deserializar embeddings a numpy arrays
            data["face_embs"] = [
                np.array(e, dtype=np.float32) for e in data.get("face_embs", [])
            ]
            return data
        except Exception:
            pass

    # No está en cache: realizar análisis
    timestamp, exif_str = get_exif_time(photo_path)
    img_rgb = load_image(photo_path, max_dim=2048)
    h0, w0 = img_rgb.shape[:2]

    # Burst ID de hardware (MakerNotes) y pHash perceptual
    burst_id = None
    try:
        burst_id = get_burst_id(str(photo_path))
    except Exception:
        pass

    phash_str = ""
    try:
        phash_str = _compute_phash(img_rgb)
    except Exception:
        pass

    # Pre-guardar miniaturas en SSD local para LightCraft
    try:
        pil_img = Image.fromarray(img_rgb)
        buf_duel = io.BytesIO()
        pil_img.save(buf_duel, format="WEBP", quality=80)
        t_duel = buf_duel.getvalue()

        pil_img.thumbnail((320, 240), Image.BILINEAR)
        buf_ui = io.BytesIO()
        pil_img.save(buf_ui, format="WEBP", quality=85)
        t_ui = buf_ui.getvalue()

        save_thumbnail_to_disk(str(photo_path), t_ui, t_duel)
    except Exception:
        pass

    # Blur score global
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Detección facial YuNet
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    detector = get_thread_yunet(w0, h0)
    confirmed_faces = []
    confirmed_boxes = []

    if detector is not None:
        _, raw_faces = detector.detect(img_bgr)
        if raw_faces is not None and len(raw_faces) > 0:
            boxes = [[int(f[0]), int(f[1]), int(f[2]), int(f[3])] for f in raw_faces]
            scores = [float(f[14]) for f in raw_faces]
            keep_idx = nms_boxes(boxes, scores, iou_thresh=0.35)
            # Descartar falsos positivos parásitos en follaje/árboles menores a 35px
            confirmed_faces = [raw_faces[i] for i in keep_idx if int(raw_faces[i][2]) >= 35 and int(raw_faces[i][3]) >= 35]
            confirmed_boxes = [[int(f[0]), int(f[1]), int(f[2]), int(f[3])] for f in confirmed_faces]

    face_sharpness = compute_face_sharpness(img_rgb, confirmed_boxes)
    face_attrs = []
    face_embs = []

    landmarker = get_thread_landmarker()
    import mediapipe as mp

    for f in confirmed_faces:
        fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
        kps = np.array(
            [[f[4], f[5]], [f[6], f[7]], [f[8], f[9]], [f[10], f[11]], [f[12], f[13]]],
            dtype=np.float32,
        )
        emb = embed_face(img_rgb, [fx, fy, fw, fh], landmarks=kps)
        face_embs.append(emb)

        # Análisis biométrico MediaPipe
        attr = {
            "ear": 0.22, "blink": 0.0, "eyes_closed": False,
            "gaze_score": 0.85, "gaze_out": False,
            "smile_score": 0.0, "smile": False,
            "valid": True, "yaw": 0.0,
        }
        if landmarker is not None:
            side = int(max(fw, fh) * 1.3)
            cx, cy = fx + fw // 2, fy + fh // 2
            x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
            x1, y1 = min(w0, cx + side // 2), min(h0, cy + side // 2)
            crop = img_rgb[y0:y1, x0:x1]
            if crop.size > 0:
                crop_512 = cv2.resize(crop, (512, 512))
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_512)
                res = landmarker.detect(mp_img)
                if res.face_landmarks:
                    attr = compute_biometric_face_attributes(res.face_landmarks[0])
                    attr["valid"] = True
                    attr["yaw"] = 0.0

        face_attrs.append(attr)

    # Generar máscaras neuronales en cache si no existen o son del formato cuadrado antiguo
    bin_files = ["person.bin", "facial_skin.bin", "eye_sclera.bin", "iris_pupil.bin", "teeth.bin"]
    masks_exist = all((target_cache_dir / b).exists() for b in bin_files)
    if masks_exist:
        p_bin = target_cache_dir / "person.bin"
        if p_bin.stat().st_size == 512 * 512:
            masks_exist = False

    if force or not masks_exist:
        generate_all_masks(str(photo_path), str(target_cache_dir), max_dim=2048)

    # Guardar meta.json serializable
    meta_dict = {
        "path": str(photo_path),
        "timestamp": timestamp,
        "exif_str": exif_str,
        "burst_id": burst_id,
        "phash": phash_str,
        "blur_score": blur_score,
        "width": w0,
        "height": h0,
        "face_bboxes": confirmed_boxes,
        "face_sharpness": face_sharpness,
        "face_attrs": face_attrs,
        "faces_detected": len(confirmed_faces),
    }

    try:
        serializable_meta = dict(meta_dict)
        serializable_meta["face_embs"] = [
            e.tolist() if isinstance(e, np.ndarray) else e for e in face_embs
        ]
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(serializable_meta, f)
    except Exception:
        pass

    meta_dict["face_embs"] = face_embs
    gc.collect()
    return meta_dict


def process_session(folder_path: Path, max_workers: int = 3, force: bool = False):
    """Procesa una sesión completa: máscaras, culling VIP y sidecars XMP."""
    if not folder_path.exists():
        print(f"[!] Carpeta no encontrada: {folder_path}")
        return

    photos = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    photos.sort(key=lambda p: p.name)
    total = len(photos)

    print(f"\n" + "=" * 65)
    print(f" PROCESANDO SESIÓN: {folder_path.name}")
    print(f" Total fotos a curar y revelar: {total}")
    print(f" Directorio: {folder_path}")
    print(f"=" * 65)

    # 1. Análisis y extracción biométrica en paralelo
    print(f"\n[Fase 1/3] Análisis biométrico y generación de máscaras...")
    t0 = time.time()
    metas = [None] * total

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(analyze_or_load_photo, p, force): i for i, p in enumerate(photos)}
        done_count = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                metas[idx] = future.result()
            except Exception as e:
                sys.stderr.write(f"\n[!] Error analizando {photos[idx].name}: {e}\n")
                # Fallback seguro
                mtime = os.path.getmtime(photos[idx])
                metas[idx] = {
                    "path": str(photos[idx]),
                    "timestamp": mtime,
                    "exif_str": "",
                    "blur_score": 500.0,
                    "face_bboxes": [],
                    "face_sharpness": [],
                    "face_attrs": [],
                    "face_embs": [],
                    "faces_detected": 0,
                }
            done_count += 1
            if done_count % 15 == 0 or done_count == total:
                fps = done_count / max(0.1, time.time() - t0)
                pct = (done_count / total) * 100
                print(f"  [{pct:5.1f}%] {done_count}/{total} fotos analizadas ({fps:.1f} fotos/s)")

    # 2. Identidades ArcFace y Detección de Protagonistas VIP
    print(f"\n[Fase 2/3] Agrupando identidades y detectando protagonistas VIP...")
    embs_by_photo = {
        i: m["face_embs"] for i, m in enumerate(metas) if m and m.get("face_embs")
    }
    identidades = group_event_identities(embs_by_photo)
    vip_ids = rank_vip_identities(identidades, top_n=3)
    vip_photo_indices = {
        i for i, ids in identidades.items() if any(vid in vip_ids for vid in ids)
    }

    # Evaluación de la regla condicional para niños pequeños (2-5 años) / VIPs serios
    vip_photos_list = list(vip_photo_indices)
    vip_smiles = 0
    for i in vip_photos_list:
        attrs = metas[i].get("face_attrs", [])
        if any(a.get("smile") or a.get("smile_score", 0) >= 0.35 for a in attrs):
            vip_smiles += 1

    vip_smile_ratio = (vip_smiles / max(1, len(vip_photos_list))) if vip_photos_list else 1.0
    vip_smile_relaxed = bool(vip_smile_ratio < 0.20)

    print(f"  - Identidades VIP identificadas: {len(vip_ids)} protagonistas (IDs: {vip_ids})")
    print(f"  - Fotos con presencia VIP: {len(vip_photo_indices)}/{total}")
    print(f"  - Tasa global de sonrisa VIP: {vip_smile_ratio:.1%}")
    if vip_smile_relaxed:
        print(f"  > [MODO ADAPTATIVO ACTIVO] Tasa de sonrisa VIP < 20% (Niño 2-5 años o perfil serio).")
        print(f"    Sonrisa opcional. Ojos abiertos y mirada directa a cámara prioritarios.")
    else:
        print(f"  > [MODO ESTÁNDAR ACTIVO] Exigencia de sonrisa VIP normal.")

    # 3. Detección de Ráfagas (Clustering temporal <= 5.0 s + Burst ID + pHash)
    sorted_indices = sorted(range(total), key=lambda i: (metas[i]["timestamp"], metas[i]["path"]))
    clusters = []
    if sorted_indices:
        current_cluster = [sorted_indices[0]]
        for prev_idx, curr_idx in zip(sorted_indices[:-1], sorted_indices[1:]):
            m_prev = metas[prev_idx]
            m_curr = metas[curr_idx]
            dt = m_curr["timestamp"] - m_prev["timestamp"]

            # Coincidencia de Burst ID físico grabado por la cámara en MakerNotes
            b_prev = m_prev.get("burst_id")
            b_curr = m_curr.get("burst_id")
            same_hw_burst = bool(b_prev is not None and b_curr is not None and b_prev == b_curr)

            # Distancia Hamming de pHash perceptual (si cambia el encuadre drásticamente > 15, no es ráfaga)
            ph_prev = m_prev.get("phash", "")
            ph_curr = m_curr.get("phash", "")
            ph_dist = 0
            if ph_prev and ph_curr and len(ph_prev) == len(ph_curr):
                try:
                    ph_dist = bin(int(ph_prev, 16) ^ int(ph_curr, 16)).count("1")
                except ValueError:
                    ph_dist = 0

            if same_hw_burst or (0.0 <= dt <= 5.0 and ph_dist <= 15):
                current_cluster.append(curr_idx)
            else:
                clusters.append(current_cluster)
                current_cluster = [curr_idx]
        clusters.append(current_cluster)

    print(f"  - Ráfagas / clusters detectados: {len(clusters)}")

    # 4. Gating Técnico y Selección de Ganadoras
    decisions = {}  # idx -> {"rating": int, "label": str, "pick": str, "reason": str}

    face_attrs_list = [metas[k]["face_attrs"] for k in range(total)]
    face_sharpness = [metas[k]["face_sharpness"] for k in range(total)]
    face_bboxes_list = [metas[k]["face_bboxes"] for k in range(total)]
    face_identities_list = [identidades.get(k, []) for k in range(total)]

    session_blurs = [m["blur_score"] for m in metas]
    p90_blur = max(10.0, float(np.percentile(session_blurs, 85))) if session_blurs else 200.0
    min_sharp_thresh = 0.20 * p90_blur

    for cluster in clusters:
        # Calcular score competitivo entre supervivientes
        def score_candidate(k: int) -> tuple[float, bool]:
            m = metas[k]
            blur_norm = min(1.0, m["blur_score"] / p90_blur)
            s = 0.40 * blur_norm
            is_vip_top = False

            if k in vip_photo_indices:
                s += 0.20
                attrs = m.get("face_attrs", [])
                eyes_ok = bool(attrs and all(not a.get("eyes_closed", False) for a in attrs))
                smile_ok = bool(attrs and any(a.get("smile", False) or a.get("smile_score", 0.0) >= 0.35 for a in attrs))
                gaze_ok = bool(attrs and any(a.get("gaze_score", 0.0) >= 0.65 for a in attrs))

                if eyes_ok:
                    s += 0.15
                if smile_ok:
                    s += 0.15
                if gaze_ok:
                    s += 0.10
                if eyes_ok and (smile_ok or vip_smile_relaxed) and gaze_ok and blur_norm >= 0.50:
                    is_vip_top = True

            return s, is_vip_top

        if len(cluster) == 1:
            i = cluster[0]
            m = metas[i]
            # Descarte técnico adaptativo al tipo de archivo (RAW vs JPG)
            if m["blur_score"] < min_sharp_thresh and m["faces_detected"] == 0:
                decisions[i] = {"rating": 0, "label": "Rojo", "pick": "-1", "reason": "Baja nitidez"}
            else:
                score, is_vip_top = score_candidate(i)
                if is_vip_top and score >= 0.80:
                    decisions[i] = {"rating": 3, "label": "Azul", "pick": "1", "reason": "Toma única VIP destacada"}
                else:
                    decisions[i] = {"rating": 2, "label": "Verde", "pick": "1", "reason": "Toma única válida"}
            continue

        # Ráfaga multi-foto: aplicar gates técnicos jerárquicos
        survivors, reasons = apply_technical_gates_explained(
            cluster,
            face_attrs_list,
            face_sharpness,
            face_bboxes_list,
            face_identities_list=face_identities_list,
            vip_identity_ids=vip_ids,
            vip_smile_relaxed=vip_smile_relaxed,
        )

        for disc_idx, reason in reasons.items():
            decisions[disc_idx] = {
                "rating": 0, "label": "Rojo", "pick": "-1",
                "reason": f"Descarte técnico ({reason})"
            }

        if not survivors:
            survivors = list(cluster)

        survivors_sorted = sorted(survivors, key=lambda k: score_candidate(k)[0], reverse=True)

        # Regla de Poda de Ráfagas del Fotógrafo:
        # Máximo 3 a 4 fotos vivas en total por ráfaga:
        # - 1 o 2 ganadoras (3★ Azul si es VIP top, 2★ Verde normal, Pick=1)
        # - 1 o 2 alternativas (0★ Sin color, Pick=0)
        # - Peores de la ráfaga (puestos 4 o 5 en adelante) -> Rechazadas (0★ Rojo, Pick=-1)
        n_surv = len(survivors_sorted)
        num_winners = 2 if (n_surv >= 8 and score_candidate(survivors_sorted[1])[0] >= 0.75) else 1
        max_alts = 2 if n_surv >= 4 else (1 if n_surv >= 2 else 0)

        # Asignar Ganadoras
        for w_idx in range(min(num_winners, n_surv)):
            k = survivors_sorted[w_idx]
            score, is_vip_top = score_candidate(k)
            if is_vip_top and score >= 0.80:
                decisions[k] = {"rating": 3, "label": "Azul", "pick": "1", "reason": "Ganadora TOP destacada"}
            else:
                decisions[k] = {"rating": 2, "label": "Verde", "pick": "1", "reason": "Ganadora de ráfaga"}

        # Asignar Alternativas limpias (0 estrellas, sin color, pick=0)
        alt_start = num_winners
        alt_end = min(n_surv, alt_start + max_alts)
        for a_idx in range(alt_start, alt_end):
            k = survivors_sorted[a_idx]
            decisions[k] = {"rating": 0, "label": "", "pick": "0", "reason": "Alternativa de ráfaga"}

        # Las peores de la ráfaga -> Rechazadas automáticamente (0 estrellas, Rojo, Pick=-1)
        for r_idx in range(alt_end, n_surv):
            k = survivors_sorted[r_idx]
            decisions[k] = {"rating": 0, "label": "Rojo", "pick": "-1", "reason": "Descarte por exceso de ráfaga"}

    # 4.1 Garantía de Cobertura de Invitados Recurrentes (Fase 6 GutoFlow)
    try:
        selected_indices = {i for i, d in decisions.items() if d["pick"] == "1"}
        score_map = {i: metas[i]["blur_score"] for i in range(total)}
        promoted = photos_for_group_coverage(
            identities_by_photo=identidades,
            selected=selected_indices,
            score_by_photo=score_map,
        )
        if promoted:
            print(f"  - Invitados recurrentes asegurados (fotos promovidas): {len(promoted)}")
            for p_idx in promoted:
                if decisions[p_idx]["pick"] != "1":
                    decisions[p_idx] = {
                        "rating": 2, "label": "Verde", "pick": "1",
                        "reason": "Promovida para cobertura de invitado clave"
                    }
    except Exception as e:
        sys.stderr.write(f"Warning en group coverage: {e}\n")

    # 5. Escritura paralela de sidecars XMP en red
    print(f"\n[Fase 3/3] Escribiendo sidecars XMP en el NAS...")
    tx0 = time.time()
    top_count = 0
    normal_count = 0
    alts_count = 0
    rejects_count = 0

    def write_xmp_task(idx: int):
        p = photos[idx]
        d = decisions[idx]
        m = metas[idx]
        xmp_p = p.with_suffix(".xmp")

        w0 = m.get("width") or 1
        h0 = m.get("height") or 1
        raw_boxes = m.get("face_bboxes", [])
        face_regions = []
        for b in raw_boxes:
            fx, fy, fw, fh = b
            face_regions.append({
                "x": (fx + fw / 2.0) / w0,
                "y": (fy + fh / 2.0) / h0,
                "w": fw / w0,
                "h": fh / h0,
            })

        generate_lightroom_xmp(
            image_path=p,
            xmp_path=xmp_p,
            auto_exp=0.0,
            rating=d["rating"],
            label=d["label"],
            pick=d["pick"],
            face_regions=face_regions,
            image_dims=(w0, h0),
        )
        return d["rating"], d["pick"]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(write_xmp_task, i) for i in range(total)]
        for f in as_completed(futures):
            r, pick = f.result()
            if r == 3:
                top_count += 1
            elif r == 2:
                normal_count += 1
            elif pick == "0":
                alts_count += 1
            else:
                rejects_count += 1

    total_time = time.time() - t0
    xmp_time = time.time() - tx0

    print(f"\n" + "-" * 65)
    print(f" RESUMEN DE CURADURÍA: {folder_path.name}")
    print(f"  • Total fotos procesadas: {total}")
    print(f"  • Top Destacadas (3 estrellas / Azul / Pick=1): {top_count} ({top_count/total*100:.1f}%)")
    print(f"  • Ganadoras Normales (2 estrellas / Verde / Pick=1): {normal_count} ({normal_count/total*100:.1f}%)")
    print(f"  • Total Seleccionadas (Pick=1): {top_count + normal_count} ({(top_count + normal_count)/total*100:.1f}%)")
    print(f"  • Alternativas de Ráfaga (0 estrellas / Sin etiqueta / Pick=0): {alts_count} ({alts_count/total*100:.1f}%)")
    print(f"  • Descartadas (0 estrellas / Rojo / Pick=-1): {rejects_count} ({rejects_count/total*100:.1f}%)")
    print(f"  • Tiempo total: {total_time/60:.2f} min (Escritura XMP: {xmp_time:.1f} s)")
    print(f"-" * 65)


def main():
    try:
        import psutil
        p = psutil.Process(os.getpid())
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Procesador masivo NAS para GutoFlow + GutoCraft")
    parser.add_argument(
        "--session",
        choices=["giler", "dayana", "gioconda", "luciana", "all"],
        default="all",
        help="Sesión a procesar (giler, dayana, gioconda, luciana o all)",
    )
    parser.add_argument("--workers", type=int, default=4, help="Hilos paralelos de trabajo")
    parser.add_argument("--force", action="store_true", help="Forzar reanálisis completo y regeneración de máscaras")
    args = parser.parse_args()

    sessions_to_run = (
        ["giler", "dayana", "gioconda"] if args.session == "all" else [args.session]
    )

    t_all = time.time()
    for s_name in sessions_to_run:
        process_session(SESSIONS[s_name], max_workers=args.workers, force=args.force)

    print(f"\n[OK] Lote completo finalizado con éxito en {(time.time() - t_all)/60:.2f} minutos.\n")


if __name__ == "__main__":
    main()
