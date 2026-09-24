import sqlite3, hashlib, sys, os
sys.path.insert(0, 'backend')
from services.app_paths import get_analysis_dir

directory = r'\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09'
dir_hash = hashlib.md5(directory.encode()).hexdigest()
db_path = get_analysis_dir() / f'{dir_hash}.db'
conn = sqlite3.connect(str(db_path))

err_count = conn.execute("SELECT COUNT(*) FROM photo_analysis WHERE error IS NOT NULL AND error != ''").fetchone()[0]
no_blur = conn.execute("SELECT COUNT(*) FROM photo_analysis WHERE blur_score IS NULL").fetchone()[0]
print(f'Records with error: {err_count}')
print(f'Records with no blur_score: {no_blur}')

errors = conn.execute("SELECT path, error FROM photo_analysis WHERE error IS NOT NULL AND error != '' LIMIT 10").fetchall()
for p, e in errors:
    fname = p.split('\\')[-1]
    print(f'  ERROR: {fname}: {e}')

# Check ANALYSIS_VERSION mismatch
from services.analysis_store import ANALYSIS_VERSION
old_version = conn.execute("SELECT COUNT(*) FROM photo_analysis WHERE version != ?", (ANALYSIS_VERSION,)).fetchone()[0]
print(f'ANALYSIS_VERSION current: {ANALYSIS_VERSION}')
print(f'Records with OLD version (will re-analyze): {old_version}')

conn.close()
