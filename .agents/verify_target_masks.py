import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

import struct
import numpy as np
from PIL import Image
from services.mask_generator import generate_all_masks

test_dir = Path("c:/Users/Guill/Documents/GUTOFLOW/backend/models/cache/test_validation")
test_dir.mkdir(parents=True, exist_ok=True)

test_images = ["IMG_0661.JPG", "IMG_0656.JPG", "IMG_0645.JPG", "IMG_0628.JPG", "IMG_0284.JPG"]
base_folder = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")

print("=== VALIDATING 5 TARGET PHOTOS WITH NEW MASK GENERATOR ===")

for name in test_images:
    img_p = base_folder / name
    out_p = test_dir / name.replace(".JPG", "")
    res = generate_all_masks(str(img_p), str(out_p))
    
    # Read person.bin
    bin_file = out_p / "person.bin"
    data = bin_file.read_bytes()
    w, h = struct.unpack("<II", data[:8])
    payload_len = len(data) - 8
    
    # Check original image size
    with Image.open(img_p) as raw_im:
        orig_w, orig_h = raw_im.size
        
    aspect_bin = w / h
    aspect_orig = orig_w / orig_h
    diff_aspect = abs(aspect_bin - aspect_orig)
    
    # Non-zero pixels
    arr = np.frombuffer(data[8:], dtype=np.uint8).reshape((h, w))
    nz_pct = np.count_nonzero(arr > 30) / (w * h) * 100.0
    
    # Check edge artifacts
    edge_max = max(np.mean(arr[:, 0]), np.mean(arr[:, -1]), np.mean(arr[0, :]), np.mean(arr[-1, :]))
    
    faces_cnt = res.get("faces_detected", 0)
    print(f"[{name}]")
    print(f"  Faces detected: {faces_cnt}")
    print(f"  Bin dimensions: w={w}, h={h} (payload: {payload_len} bytes == {w*h})")
    print(f"  Aspect ratio: Bin={aspect_bin:.3f} vs Orig={aspect_orig:.3f} (delta={diff_aspect:.4f})")
    print(f"  Person coverage: {nz_pct:.2f}% | Edge border artifact: {edge_max:.2f}")
