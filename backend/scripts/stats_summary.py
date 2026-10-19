import sys
import sqlite3
import json
from collections import Counter
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from services.app_paths import get_user_data_dir

db_path = get_user_data_dir() / "history.db"

conn = sqlite3.connect(db_path)

# Eventos
events = [r[0] for r in conn.execute("SELECT DISTINCT scene FROM history WHERE scene != ''").fetchall()]

# Métricas de entregas
devs = conn.execute("SELECT develop FROM history WHERE label='positive' AND source LIKE 'delivered_export%'").fetchall()
cameras = Counter()
lenses = Counter()
focals = []
fstops = []
isos = []

for (d_raw,) in devs:
    try:
        d = json.loads(d_raw)
        if d.get('Camera'):
            cameras[d['Camera']] += 1
        if d.get('Lens'):
            lenses[d['Lens']] += 1
        if d.get('Focal'):
            focals.append(float(d['Focal']))
        if d.get('FStop'):
            fstops.append(float(d['FStop']))
        if d.get('ISO'):
            isos.append(int(d['ISO']))
    except Exception:
        pass

print("EVENTOS_TOTAL:", len(events))
print("TOP_CAMARAS:", cameras.most_common(4))
print("TOP_LENTES:", lenses.most_common(4))
if focals:
    print(f"FOCAL_MEDIA: {sum(focals)/len(focals):.1f}mm (Rango frecuente: {int(sorted(focals)[len(focals)//4])}mm - {int(sorted(focals)[3*len(focals)//4])}mm)")
    print(f"FSTOP_MEDIO: f/{sum(fstops)/len(fstops):.2f}")
    print(f"ISO_MEDIO: {int(sum(isos)/len(isos))}")
