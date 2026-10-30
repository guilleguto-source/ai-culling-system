import re
from pathlib import Path

p = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler\IMG_0001.JPG")
print(f"Reading {p}...", flush=True)

with open(p, "rb") as f:
    data = f.read(2 * 1024 * 1024)

print(f"Read {len(data)} bytes.", flush=True)
match = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", data, re.DOTALL)
if match:
    xmp_str = match.group(0).decode("utf-8", errors="ignore")
    print(f"Found XMP! Length: {len(xmp_str)}", flush=True)
    for line in xmp_str.splitlines():
        if any(k in line for k in ["Rating", "Pick", "Crop", "Label", "title"]):
            print(f"  {line.strip()}", flush=True)
else:
    print("No XMP packet found in first 2MB.", flush=True)
