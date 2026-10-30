"""
apply_v3_to_sessions.py — Despliegue de GutoFlow v3.0 a las sesiones Gioconda y Dayana.
Inyecta mwg-rs:Regions y crs:MaskGroupBasedCorrections con culling v3.0 adaptativo.
"""
import sys
import os
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.xmp_exporter import write_xmp, _build_xmp_packet

CACHE_DIR = BACKEND_DIR / "models" / "cache" / "mattes"

TARGET_SESSIONS = {
    "Gioconda": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Gioconda"),
    "Dayana": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Dayana"),
}

def key_normalized(p_str: str) -> str:
    norm = p_str.replace("\\", "/").lower()
    h = 0xcbf29ce484222325
    for b in norm.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return f"{h:016x}"

def key_raw(p_str: str) -> str:
    h = 0xcbf29ce484222325
    for b in p_str.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return f"{h:016x}"

def load_meta(photo_path: Path) -> dict:
    p_str = str(photo_path)
    for k in (key_normalized(p_str), key_raw(p_str)):
        m_file = CACHE_DIR / k / "meta.json"
        if m_file.exists():
            try:
                with open(m_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {
        "path": p_str,
        "timestamp": os.path.getmtime(photo_path),
        "blur_score": 500.0,
        "width": 4000,
        "height": 3000,
        "face_bboxes": [],
        "face_attrs": [],
        "face_embs": [],
        "faces_detected": 0,
    }

def process_session(name: str, session_path: Path):
    print("=" * 65)
    print(f"PROCESANDO SESION v3.0: {name.upper()}")
    print(f"Ruta: {session_path}")
    print("=" * 65)

    photos = [p for p in session_path.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".cr2")]
    photos.sort(key=lambda p: p.name)
    total = len(photos)
    print(f"Total fotos: {total}")

    # 1. Cargar metadatos en paralelo
    t0 = time.time()
    metas = [None] * total
    with ThreadPoolExecutor(max_workers=8) as ex:
        future_to_idx = {ex.submit(load_meta, p): i for i, p in enumerate(photos)}
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            metas[idx] = fut.result()

    t_load = time.time() - t0
    print(f"Metadatos biométricos cargados en {t_load:.2f} s")

    # 2. Clustering de ráfagas
    sorted_indices = sorted(range(total), key=lambda i: (metas[i].get("timestamp", 0), metas[i]["path"]))
    clusters = []
    if sorted_indices:
        current_cluster = [sorted_indices[0]]
        for prev_idx, curr_idx in zip(sorted_indices[:-1], sorted_indices[1:]):
            m_prev = metas[prev_idx]
            m_curr = metas[curr_idx]
            dt = m_curr.get("timestamp", 0) - m_prev.get("timestamp", 0)
            same_burst = (m_prev.get("burst_id") and m_curr.get("burst_id") and m_prev["burst_id"] == m_curr["burst_id"])
            if same_burst or dt <= 3.5:
                current_cluster.append(curr_idx)
            else:
                clusters.append(current_cluster)
                current_cluster = [curr_idx]
        if current_cluster:
            clusters.append(current_cluster)

    print(f"Total agrupaciones/ráfagas: {len(clusters)}")

    # 3. Culling v3.0 (Hero Shot Yaw < 15°, EAR blink veto)
    decisions = {}
    for cluster in clusters:
        if len(cluster) == 1:
            idx = cluster[0]
            decisions[idx] = {"stars": 2, "label": "selected", "pick": "1", "color": "Verde"}
            continue

        scored = []
        for idx in cluster:
            m = metas[idx]
            blur = m.get("blur_score", 500.0)
            attrs = m.get("face_attrs", [])
            faces_cnt = m.get("faces_detected", 0)

            # EAR parpadeo
            eyes_open = True
            for a in attrs:
                if a.get("ear", 0.25) < 0.17 or a.get("closed_eyes"):
                    eyes_open = False

            # Yaw mirada frontal
            gaze_frontal = any(abs(a.get("yaw", 30.0)) < 15.0 for a in attrs)
            smile = max([a.get("smile_score", 0.0) for a in attrs], default=0.0)

            if not eyes_open and faces_cnt > 0:
                scored.append((idx, -100.0, "pestañeo"))
                continue

            score = (blur * 0.45) + (smile * 250.0)
            if gaze_frontal:
                score += 350.0
            scored.append((idx, score, "ok"))

        scored.sort(key=lambda x: x[1], reverse=True)
        winner_idx = scored[0][0]

        for idx, sc, rz in scored:
            if idx == winner_idx and sc > 0:
                decisions[idx] = {"stars": 3, "label": "selected", "pick": "1", "color": "Azul"}
            elif sc < 0:
                decisions[idx] = {"stars": 0, "label": "closed_eyes", "pick": "-1", "color": "Rojo"}
            else:
                decisions[idx] = {"stars": 0, "label": "neutral", "pick": "0", "color": ""}

    # 4. Escritura XMP v3.0 en red
    tx0 = time.time()
    def write_one_xmp(idx):
        p = photos[idx]
        d = decisions[idx]
        m = metas[idx]
        w0 = m.get("width") or 4000
        h0 = m.get("height") or 3000
        face_regions = []
        for b in m.get("face_bboxes", []):
            if len(b) == 4:
                fx, fy, fw, fh = b
                face_regions.append({
                    "x": (fx + fw / 2.0) / w0,
                    "y": (fy + fh / 2.0) / h0,
                    "w": fw / w0,
                    "h": fh / h0,
                })

        xmp_p = p.with_suffix(".xmp")
        packet = _build_xmp_packet(
            stars=d["stars"],
            color=d["color"],
            label=d["label"],
            flag="pick" if d["pick"] == "1" else ("reject" if d["pick"] == "-1" else "none"),
            face_regions=face_regions,
            image_dims=(w0, h0),
            include_anatomical_masks=bool(d["stars"] >= 2 or d["label"] == "selected"),
        )
        xmp_p.write_bytes(packet)
        return d["stars"], d["pick"]

    written_count = 0
    top_picks = 0
    normal_picks = 0
    rejects = 0

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(write_one_xmp, i) for i in range(total)]
        for f in as_completed(futures):
            stars, pick = f.result()
            written_count += 1
            if stars == 3:
                top_picks += 1
            elif stars == 2:
                normal_picks += 1
            elif pick == "-1":
                rejects += 1

    t_xmp = time.time() - tx0
    print(f"Escritura XMP v3.0 completada en {t_xmp:.2f} s ({written_count}/{total} sidecars)")
    print(f"Resumen de Curaduría:")
    print(f"  • 3★ Azul (Top Hero Shot / VIP): {top_picks} ({top_picks/total*100:.1f}%)")
    print(f"  • 2★ Verde (Picks ganadores):     {normal_picks} ({normal_picks/total*100:.1f}%)")
    print(f"  • Total Seleccionadas:            {top_picks + normal_picks} ({(top_picks + normal_picks)/total*100:.1f}%)")
    print(f"  • 0★ Rojo (Rechazos por parpadeo): {rejects} ({rejects/total*100:.1f}%)")
    print(f"  • 0★ Neutro (Alternativas ráfaga): {total - (top_picks + normal_picks + rejects)}")
    print(f"Tiempo total sesión: {(time.time() - t0):.2f} s\n")

def main():
    t_start = time.time()
    for name, path in TARGET_SESSIONS.items():
        if path.exists():
            process_session(name, path)
        else:
            print(f"Ruta no encontrada: {path}")
    print("=" * 65)
    print(f"TODAS LAS SESIONES ACTUALIZADAS A v3.0 EN {time.time() - t_start:.2f} s")
    print("=" * 65)

if __name__ == "__main__":
    main()
