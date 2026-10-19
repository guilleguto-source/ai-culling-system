import sqlite3, hashlib, json, sys
sys.path.insert(0, 'backend')
sys.stdout.reconfigure(encoding='utf-8')
from services.app_paths import get_analysis_dir

directory = r'\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09'
dir_hash = hashlib.md5(directory.encode()).hexdigest()
db_path = get_analysis_dir() / f'{dir_hash}.db'
conn = sqlite3.connect(str(db_path))

rows = conn.execute('''
    SELECT path, closed_eyes_count, looking_away_count, face_count, face_attrs, version
    FROM photo_analysis 
    WHERE closed_eyes_count > 0 
    LIMIT 10
''').fetchall()

print('Sample of records with closed_eyes_count > 0:')
for row in rows:
    fname = row[0].split('\\')[-1]
    fa = json.loads(row[4]) if row[4] else []
    # show ear values in face_attrs
    ears = [f.get('ear', 'N/A') for f in fa]
    eyes_closed = [f.get('eyes_closed', False) for f in fa]
    print(f'  {fname}: closed_ct={row[1]}, looking_away={row[2]}, faces={row[3]}, v={row[5]}')
    print(f'    face_attrs EAR values: {ears}')
    print(f'    face_attrs eyes_closed: {eyes_closed}')

total_closed = conn.execute('SELECT COUNT(*) FROM photo_analysis WHERE closed_eyes_count > 0').fetchone()[0]
total_faces = conn.execute('SELECT COUNT(*) FROM photo_analysis WHERE face_count > 0').fetchone()[0]
total = conn.execute('SELECT COUNT(*) FROM photo_analysis').fetchone()[0]

print(f'\nTotal photos: {total}')
print(f'Photos with faces detected: {total_faces}')
print(f'Photos with closed_eyes_count > 0: {total_closed} ({100*total_closed/total:.1f}%)')

dist = conn.execute('SELECT closed_eyes_count, COUNT(*) FROM photo_analysis GROUP BY closed_eyes_count ORDER BY closed_eyes_count').fetchall()
print(f'\nclosed_eyes_count distribution:')
for val, cnt in dist:
    print(f'  {val} eyes closed: {cnt} fotos')

# Also check face_count distribution
fdist = conn.execute('SELECT face_count, COUNT(*) FROM photo_analysis GROUP BY face_count ORDER BY face_count').fetchall()
print(f'\nface_count distribution:')
for val, cnt in fdist:
    print(f'  {val} faces: {cnt} fotos')

conn.close()
