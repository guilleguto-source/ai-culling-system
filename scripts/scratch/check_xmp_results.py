import os, json, hashlib
from pathlib import Path
import sys
sys.path.insert(0, 'backend')
from services.app_paths import get_analysis_dir

directory = Path(r'\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09')
xmp_files = list(directory.glob('*.xmp')) + list(directory.glob('*.XMP'))
print(f'Total XMP sidecars in directory: {len(xmp_files)}')

ratings = {}
colors = {}

for xmp_p in xmp_files:
    try:
        content = xmp_p.read_text(encoding='utf-8', errors='ignore')
        rating = None
        color = None
        if 'Rating=' in content:
            r_part = content.split('Rating=')[1]
            r_str = r_part[1:].split(r_part[0])[0]
            rating = int(r_str)
        if 'Label=' in content:
            l_part = content.split('Label=')[1]
            color = l_part[1:].split(l_part[0])[0]
        
        ratings[rating] = ratings.get(rating, 0) + 1
        if color:
            colors[color] = colors.get(color, 0) + 1
    except Exception as e:
        pass

print('\nRatings distribution in XMP sidecars:')
for r, c in sorted(ratings.items(), key=lambda x: (x[0] is None, x[0])):
    print(f'  Stars {r}: {c}')

print('\nColor labels distribution in XMP sidecars:')
for col, c in sorted(colors.items()):
    print(f'  Color {col}: {c}')

# Check backup manifest in undo_export
from services.undo_export import _event_dir, MANIFEST
b_dir = _event_dir(str(directory))
mf = b_dir / MANIFEST
print(f'\nBackup manifest exists: {mf.exists()}')
if mf.exists():
    b_data = json.loads(mf.read_text(encoding='utf-8'))
    print(f'Backup manifest items count: {len(b_data)}')

# Check snapshots
snapshots = list(get_analysis_dir().glob('*_snapshot.json'))
print(f'\nTotal snapshots found: {len(snapshots)}')
for s in snapshots:
    print('  Snapshot:', s.name)
