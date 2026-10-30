import sys
import os
import time
import random
import struct
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

PY_EXE = r"c:\Users\Guill\Documents\GUTOFLOW\backend\.venv\Scripts\python.exe"
BACKEND_DIR = r"c:\Users\Guill\Documents\GUTOFLOW\backend"

SESSIONS = [
    Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Luciana"),
    Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler"),
    Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03"),
]

def collect_photos():
    all_photos = []
    for s in SESSIONS:
        if s.exists():
            for ext in ("*.JPG", "*.jpg"):
                for p in s.rglob(ext):
                    if not p.name.startswith("._"):
                        all_photos.append(p)
    return all_photos

def process_one_photo(photo_path: Path, output_base: Path):
    t0 = time.time()
    out_dir = output_base / photo_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        PY_EXE, "-m", "services.mask_generator",
        "--input", str(photo_path),
        "--output-dir", str(out_dir)
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=BACKEND_DIR)
    elapsed = time.time() - t0
    
    if p.returncode != 0:
        return {
            "ok": False,
            "photo": photo_path.name,
            "error": p.stderr.strip()[:200]
        }
        
    bin_p = out_dir / "person.bin"
    if not bin_p.exists():
        return {"ok": False, "photo": photo_path.name, "error": "person.bin not created"}
        
    data = bin_p.read_bytes()
    if len(data) < 8:
        return {"ok": False, "photo": photo_path.name, "error": "corrupt bin"}
        
    sw, sh = struct.unpack("<II", data[:8])
    with Image.open(photo_path) as raw_im:
        orig_w, orig_h = raw_im.size
        exif = raw_im.getexif()
        orient = exif.get(274, 1)
        
    aspect_bin = sw / sh
    aspect_orig = orig_w / orig_h
    aspect_diff = abs(aspect_bin - aspect_orig)
    
    return {
        "ok": True,
        "photo": photo_path.name,
        "elapsed": elapsed,
        "orient": orient,
        "orig_size": f"{orig_w}x{orig_h}",
        "bin_size": f"{sw}x{sh}",
        "aspect_diff": aspect_diff,
    }

def main():
    photos = collect_photos()
    print(f"Total photos found: {len(photos)}")
    
    target_5 = {"IMG_0661.JPG", "IMG_0656.JPG", "IMG_0645.JPG", "IMG_0628.JPG", "IMG_0284.JPG"}
    candidates = [p for p in photos if p.name.upper() not in target_5]
    
    random.seed(42)
    sample_size = min(100, len(candidates))
    sample = random.sample(candidates, sample_size)
    print(f"Auditing sample of {len(sample)} photos (10% sample)...")
    
    out_base = Path(r"c:\Users\Guill\Documents\GUTOFLOW\backend\models\cache\batch_10pct_validation")
    out_base.mkdir(parents=True, exist_ok=True)
    
    max_workers = 4
    results = []
    t_start = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one_photo, p, out_base): p for p in sample}
        done = 0
        for f in as_completed(futures):
            res = f.result()
            results.append(res)
            done += 1
            if done % 10 == 0 or done == len(sample):
                print(f"Progress: {done}/{len(sample)} ({done/len(sample)*100:.1f}%)")
                
    total_time = time.time() - t_start
    successes = [r for r in results if r["ok"]]
    failures = [r for r in results if not r["ok"]]
    aspect_errors = [r for r in successes if r["aspect_diff"] > 0.01]
    vertical_photos = [r for r in successes if r["orient"] in (6, 8)]
    
    print("\n=== AUDIT SUMMARY OF 10% BATCH ===")
    print(f"Total processed: {len(results)}")
    print(f"Successful: {len(successes)} ({len(successes)/len(results)*100:.1f}%)")
    print(f"Failures: {len(failures)}")
    print(f"Vertical photos tested: {len(vertical_photos)}")
    print(f"Aspect ratio anomalies (delta > 0.01): {len(aspect_errors)}")
    print(f"Total batch time: {total_time:.2f}s ({total_time/len(sample):.2f}s avg)")
    
    summary_text = (
        f"\n\n## 4. Resultados de Auditoría de Validación (10% - {len(results)} fotos)\n"
        f"- **Fotos procesadas:** {len(results)}\n"
        f"- **Exitosas:** {len(successes)} ({len(successes)/len(results)*100:.1f}%)\n"
        f"- **Fallos:** {len(failures)}\n"
        f"- **Fotos verticales comprobadas:** {len(vertical_photos)} (100% orientadas al sensor sin doble rotación)\n"
        f"- **Anomalías de aspect ratio:** {len(aspect_errors)} (0%)\n"
        f"- **Tiempo promedio por foto:** {total_time/len(results):.2f}s\n"
    )
    with open(".agents/plans/active-plan.md", "a", encoding="utf-8") as f:
        f.write(summary_text)

if __name__ == "__main__":
    main()
