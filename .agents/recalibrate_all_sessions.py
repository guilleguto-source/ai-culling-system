"""
recalibrate_all_sessions.py — Recalibración oficial de 2★ (Verde) vs 3★ (Azul).
Aplica la jerarquía real de GutoFlow en Dayana, Gioconda y Giler:
- 2★ Verde (Pick=1): Ganador estándar de cada ráfaga o escena.
- 3★ Azul (Pick=1): Hero Shot excepcional (solo VIP, Yaw < 15°, ojos abiertos, percentil alto).
- 2★ Verde (Pick=1): Segundo pick en ráfagas de >= 5 fotos con alta calidad.
- 0★ Neutro (Pick=0): Alternativas limpias de ráfaga.
- 0★ Rojo (Pick=-1): Descartes por pestañeo o blur crítico.
Preserva mwg-rs:Regions y las 5 máscaras en fotos seleccionadas.
"""
import sys
import os
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.xmp_exporter import _build_xmp_packet
from services.face_identity import group_event_identities, rank_vip_identities

CACHE_DIR = BACKEND_DIR / "models" / "cache" / "mattes"

SESSIONS = {
    "Dayana": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Dayana"),
    "Gioconda": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Gioconda"),
    "Giler": Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler"),
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
                    data = json.load(f)
                data["face_embs"] = [np.array(e, dtype=np.float32) for e in data.get("face_embs", [])]
                return data
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
    print(f"RECALIBRANDO SESION: {name.upper()}")
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
    print(f"Metadatos cargados en {t_load:.2f} s")

    # 2. Agrupamiento de identidades VIP
    embs_by_photo = {i: m["face_embs"] for i, m in enumerate(metas) if m and m.get("face_embs")}
    identidades = group_event_identities(embs_by_photo)
    vip_ids = rank_vip_identities(identidades, top_n=3)
    vip_photo_indices = {i for i, ids in identidades.items() if any(vid in vip_ids for vid in ids)}
    print(f"Fotos con presencia de protagonistas VIP: {len(vip_photo_indices)}/{total}")

    # 3. Clustering de ráfagas
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

    print(f"Total ráfagas/agrupaciones: {len(clusters)}")

    # 4. Cálculo de percentil de nitidez para detectar fotos de élite
    blur_scores = [m.get("blur_score", 0.0) for m in metas]
    p85_blur = max(100.0, float(np.percentile(blur_scores, 85))) if blur_scores else 300.0

    # 5. Culling calibrado (2★ Verde por defecto, 3★ Azul para Hero Shots exclusivos)
    decisions = {}

    for cluster in clusters:
        if len(cluster) == 1:
            idx = cluster[0]
            m = metas[idx]
            attrs = m.get("face_attrs", [])
            eyes_open = not any(a.get("ear", 0.25) < 0.17 or a.get("closed_eyes") for a in attrs)
            if not eyes_open and m.get("faces_detected", 0) > 0:
                decisions[idx] = {"stars": 0, "label": "closed_eyes", "pick": "-1", "color": "Rojo"}
            else:
                # Tomas únicas son 2★ Verde por defecto, salvo que sea un Hero Shot VIP perfecto
                is_vip = idx in vip_photo_indices
                gaze_frontal = any(abs(a.get("yaw", 30.0)) < 15.0 for a in attrs)
                if is_vip and gaze_frontal and m.get("blur_score", 0) >= p85_blur:
                    decisions[idx] = {"stars": 3, "label": "selected", "pick": "1", "color": "Azul"}
                else:
                    decisions[idx] = {"stars": 2, "label": "selected", "pick": "1", "color": "Verde"}
            continue

        # Evaluación de ráfaga
        survivors = []
        for idx in cluster:
            m = metas[idx]
            attrs = m.get("face_attrs", [])
            faces_cnt = m.get("faces_detected", 0)

            # Veto de parpadeo
            eyes_open = True
            min_ear = 1.0
            for a in attrs:
                ear = a.get("ear", 0.25)
                min_ear = min(min_ear, ear)
                if ear < 0.17 or a.get("closed_eyes"):
                    eyes_open = False

            if not eyes_open and faces_cnt > 0:
                decisions[idx] = {"stars": 0, "label": "closed_eyes", "pick": "-1", "color": "Rojo"}
                continue

            # Puntuación técnica
            blur = m.get("blur_score", 0.0)
            gaze_frontal = any(abs(a.get("yaw", 30.0)) < 15.0 for a in attrs)
            smile = max([a.get("smile_score", 0.0) for a in attrs], default=0.0)
            is_vip = idx in vip_photo_indices

            score = (blur * 0.40) + (smile * 200.0)
            if gaze_frontal:
                score += 300.0
            if is_vip:
                score += 150.0

            survivors.append({
                "idx": idx,
                "score": score,
                "blur": blur,
                "gaze_frontal": gaze_frontal,
                "is_vip": is_vip,
                "min_ear": min_ear,
                "smile": smile,
            })

        if not survivors:
            # Si todas pestañearon, marcar la de mayor apertura como neutra
            for idx in cluster:
                if idx not in decisions:
                    decisions[idx] = {"stars": 0, "label": "neutral", "pick": "0", "color": ""}
            continue

        survivors.sort(key=lambda x: x["score"], reverse=True)

        # Regla GutoFlow Oficial:
        # Ganador de ráfaga es 2★ Verde por defecto.
        # Solo se promueve a 3★ Azul si es un HERO SHOT VIP excepcional:
        # (Protagonista VIP + Mirada Frontal Yaw < 15° + Ojos bien abiertos EAR >= 0.22 + Alta nitidez)
        winner = survivors[0]
        w_idx = winner["idx"]
        is_hero_shot = (
            winner["is_vip"] and
            winner["gaze_frontal"] and
            winner["min_ear"] >= 0.22 and
            winner["blur"] >= (p85_blur * 0.85)
        )

        if is_hero_shot:
            decisions[w_idx] = {"stars": 3, "label": "selected", "pick": "1", "color": "Azul"}
        else:
            decisions[w_idx] = {"stars": 2, "label": "selected", "pick": "1", "color": "Verde"}

        # En ráfagas largas (>= 5 fotos), dar 2★ Verde al segundo pick si es de alta calidad
        n_surv = len(survivors)
        has_second_pick = False
        if n_surv >= 5 and survivors[1]["score"] >= (winner["score"] * 0.75):
            sec_idx = survivors[1]["idx"]
            decisions[sec_idx] = {"stars": 2, "label": "selected", "pick": "1", "color": "Verde"}
            has_second_pick = True

        # Resto de supervivientes -> 0★ Neutro (Alternativas limpias)
        start_alt = 2 if has_second_pick else 1
        for s in survivors[start_alt:]:
            decisions[s["idx"]] = {"stars": 0, "label": "neutral", "pick": "0", "color": ""}

    # 6. Escribir sidecars XMP definitivos en el NAS
    tx0 = time.time()
    def write_recalibrated_xmp(idx):
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
            include_anatomical_masks=bool(d["stars"] >= 2),
        )
        xmp_p.write_bytes(packet)
        return d["stars"], d["pick"]

    top_3 = 0
    pick_2 = 0
    reject_0 = 0
    alt_0 = 0

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(write_recalibrated_xmp, i) for i in range(total)]
        for f in as_completed(futures):
            stars, pick = f.result()
            if stars == 3:
                top_3 += 1
            elif stars == 2:
                pick_2 += 1
            elif pick == "-1":
                reject_0 += 1
            else:
                alt_0 += 1

    t_xmp = time.time() - tx0
    print(f"Escritura XMP completada en {t_xmp:.2f} s")
    print(f"DISTRIBUCION FINAL CALIBRADA:")
    print(f"  • 3★ Azul (Hero Shots VIP exclusivos): {top_3} ({top_3/total*100:.1f}%)")
    print(f"  • 2★ Verde (Picks ganadores estándar):  {pick_2} ({pick_2/total*100:.1f}%)")
    print(f"  • TOTAL SELECCIONADAS (Pick=1):        {top_3 + pick_2} ({(top_3 + pick_2)/total*100:.1f}%)")
    print(f"  • 0★ Rojo (Descartes por parpadeo):    {reject_0} ({reject_0/total*100:.1f}%)")
    print(f"  • 0★ Neutro (Alternativas de ráfaga):   {alt_0} ({alt_0/total*100:.1f}%)")
    print(f"Tiempo total sesión: {time.time() - t0:.2f} s\n")

def main():
    t_start = time.time()
    for name, path in SESSIONS.items():
        if path.exists():
            process_session(name, path)
        else:
            print(f"Ruta no encontrada: {path}")
    print("=" * 65)
    print(f"RECALIBRACION COMPLETADA EN TODAS LAS SESIONES EN {time.time() - t_start:.2f} s")
    print("=" * 65)

if __name__ == "__main__":
    main()
