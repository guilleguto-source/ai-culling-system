"""
Renderiza exclusivamente las 30 láminas 4K de la selección de élite
obtenida del simulacro completo de la sesión Giler.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from cull_lab.experiments.generate_desktop_audit import process_and_render_audit_sheet

NAS_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
REPORT_PATH = Path(r"C:\Users\Guill\Desktop\GutoFlow_New_Culling_XMP\culling_statistics_report.json")

with open(REPORT_PATH, "r", encoding="utf-8") as f:
    report = json.load(f)

elite_names = report["elite_30_filenames"]
print(f"Iniciando renderizado 4K de las {len(elite_names)} fotos cumbre...")

for idx, fname in enumerate(elite_names, 1):
    photo_path = NAS_DIR / fname
    if not photo_path.exists():
        print(f"[{idx:02d}/30] No encontrada: {fname}")
        continue

    situation = f"Hero Shot VIP #{idx} - Momento Cumbre (3 Estrellas)"
    try:
        res = process_and_render_audit_sheet(photo_path, situation, idx, len(elite_names))
        print(f"[{idx:02d}/30] Generada {Path(res['output_image']).name} ({fname})")
    except Exception as e:
        print(f"[{idx:02d}/30] Error renderizando {fname}: {e}")

print("Renderizado de las 30 fotos cumbre completado.")
