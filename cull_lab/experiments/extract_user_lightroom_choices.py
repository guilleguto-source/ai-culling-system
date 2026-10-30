import os
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

NAS_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
OUTPUT_JSON = Path(r"cull_lab\experiments\user_lightroom_giler.json")

def inspect_jpg_xmp(file_path: Path):
    try:
        with open(file_path, "rb") as f:
            data = f.read(256 * 1024)
        match = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", data, re.DOTALL)
        if match:
            xmp_str = match.group(0).decode("utf-8", errors="ignore")
            # Rating
            r_match = re.search(r'Rating="(\d+)"', xmp_str)
            if not r_match:
                r_match = re.search(r'<xmp:Rating>(\d+)</xmp:Rating>', xmp_str)
            rating = int(r_match.group(1)) if r_match else 0
            
            # Pick
            p_match = re.search(r'Pick="(-?\d+)"', xmp_str)
            if not p_match:
                p_match = re.search(r'<crs:Pick>(-?\d+)</crs:Pick>', xmp_str)
            if not p_match:
                p_match = re.search(r'<xmp:Pick>(-?\d+)</xmp:Pick>', xmp_str)
            pick = int(p_match.group(1)) if p_match else 0
            
            # Label
            lbl_match = re.search(r'Label="([^"]+)"', xmp_str)
            if not lbl_match:
                lbl_match = re.search(r'<xmp:Label>([^<]+)</xmp:Label>', xmp_str)
            label = lbl_match.group(1) if lbl_match else ""

            # Crop
            has_crop = ("CropTop" in xmp_str or "CropAngle" in xmp_str)
            return {
                "name": file_path.name,
                "rating": rating,
                "pick": pick,
                "label": label,
                "has_crop": has_crop,
                "found_xmp": True
            }
    except Exception as e:
        pass
    return {
        "name": file_path.name,
        "rating": 0,
        "pick": 0,
        "label": "",
        "has_crop": False,
        "found_xmp": False
    }

def main():
    t0 = time.time()
    print("Iniciando extracción multi-hilo de elecciones de Lightroom desde los JPGs del NAS...", flush=True)
    jpg_files = sorted(list(NAS_DIR.glob("*.JPG")))
    print(f"Total JPGs encontrados: {len(jpg_files)}", flush=True)
    
    user_choices = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(inspect_jpg_xmp, f): f for f in jpg_files}
        for fut in as_completed(futures):
            res = fut.result()
            user_choices[res["name"]] = res
            
    # Ordenar por nombre
    user_choices = dict(sorted(user_choices.items()))
    
    rating_counts = {}
    pick_counts = {}
    label_counts = {}
    for d in user_choices.values():
        r = d["rating"]
        p = d["pick"]
        l = d["label"]
        rating_counts[r] = rating_counts.get(r, 0) + 1
        pick_counts[p] = pick_counts.get(p, 0) + 1
        if l:
            label_counts[l] = label_counts.get(l, 0) + 1
            
    selected_stars = sum(1 for d in user_choices.values() if d["rating"] >= 1)
    picked_flags = sum(1 for d in user_choices.values() if d["pick"] == 1)
    rejected_flags = sum(1 for d in user_choices.values() if d["pick"] == -1)
    unflagged = sum(1 for d in user_choices.values() if d["pick"] == 0 and d["rating"] == 0)
    
    elapsed = time.time() - t0
    print(f"\n--- Resumen de Elecciones Reales del Usuario en Lightroom (Tiempo: {elapsed:.2f}s) ---", flush=True)
    print(f"Total fotos procesadas: {len(user_choices)}", flush=True)
    print(f"Distribución de Estrellas (Rating): {dict(sorted(rating_counts.items()))}", flush=True)
    print(f"Distribución de Flags (Pick): {dict(sorted(pick_counts.items()))}", flush=True)
    if label_counts:
        print(f"Distribución de Etiquetas de Color: {label_counts}", flush=True)
    print(f"Fotos con Estrellas (>= 1*): {selected_stars}", flush=True)
    print(f"Fotos Aprobadas (Pick = 1): {picked_flags}", flush=True)
    print(f"Fotos Rechazadas (Pick = -1): {rejected_flags}", flush=True)
    print(f"Fotos Neutras / Descartadas implicitas (0* y Pick = 0): {unflagged}", flush=True)
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(user_choices, f, indent=2)
    print(f"Archivo guardado en: {OUTPUT_JSON}", flush=True)

if __name__ == "__main__":
    main()
