"""
Simulate EXACTLY what the culling pipeline does and time each step.
This script runs the full pipeline logic step by step with logging.
"""
import sys, os, time, logging
sys.path.insert(0, 'backend')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('pipeline_sim')

from pathlib import Path
from services.ingester import get_ingest_tasks, process_single_image, ImageRecord, RAW_EXTENSIONS
from services.analysis_store import init_store, load_analysis
from services.thumbnail_store import get_thumbnail_cache_paths
from services.analysis import analyze_photo, PhotoAnalysis

directory = r'\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09'

print("=== STEP 1: Discovering tasks ===")
t0 = time.time()
tasks = get_ingest_tasks(directory)
print(f"  {len(tasks)} tasks in {time.time()-t0:.2f}s")

print("\n=== STEP 2: Open DB ===")
conn = init_store(directory)
print("  DB opened")

BATCH_SIZE = 200
records = []
analyses = []
errors = 0

print(f"\n=== STEP 3: BATCH LOOP ({len(tasks)} files, batch_size={BATCH_SIZE}) ===")
for batch_start in range(0, len(tasks), BATCH_SIZE):
    batch_tasks = tasks[batch_start:batch_start + BATCH_SIZE]
    batch_records = []
    to_process = []

    # Phase 1: Check cache
    t_batch = time.time()
    for path, linked_raw in batch_tasks:
        current_mtime = 0
        try: current_mtime = os.path.getmtime(path)
        except: pass
        ans = load_analysis(conn, str(path), current_mtime)
        ui_path, duel_path = get_thumbnail_cache_paths(str(path))
        if ans and ui_path.exists() and duel_path.exists():
            rec = ImageRecord(
                path=str(path), filename=path.name,
                is_raw=path.suffix.lower() in RAW_EXTENSIONS,
                linked_raw_path=linked_raw, phash=ans.phash, exif_datetime=ans.exif_datetime
            )
            batch_records.append(rec)
        else:
            to_process.append((path, linked_raw))

    print(f"\n  Batch {batch_start//BATCH_SIZE+1}: {len(batch_records)} cached, {len(to_process)} to process ({time.time()-t_batch:.2f}s)")

    # Phase 2: Process uncached
    if to_process:
        print(f"    Processing {len(to_process)} uncached files...")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        t_proc = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_single_image, p, lr): p for p, lr in to_process}
            for future in as_completed(futures):
                rec = future.result()
                batch_records.append(rec)
                if rec.error:
                    errors += 1
        print(f"    Done processing in {time.time()-t_proc:.2f}s")

    batch_records.sort(key=lambda r: r.path)

    # Phase 3: Analysis
    print(f"    Analyzing {len(batch_records)} records...")
    t_ana = time.time()
    
    import concurrent.futures
    for i, record in enumerate(batch_records):
        global_idx = len(records)
        current_mtime = os.path.getmtime(record.path) if not record.error else 0.0
        ans = load_analysis(conn, record.path, current_mtime)
        
        if record.error:
            # This path should be quick since analyze_photo returns immediately for error records
            ans = PhotoAnalysis(path=record.path, index=global_idx, is_raw=record.is_raw, error=True)
        elif not ans:
            # Needs analysis
            print(f"      [WARN] Photo {record.path} needs analysis but should be cached!")
            exe = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            f = exe.submit(analyze_photo, global_idx, record, None, None, 100.0, True, True)
            try:
                ans = f.result(timeout=45)
            except concurrent.futures.TimeoutError:
                print(f"      [TIMEOUT] {record.path}")
                ans = PhotoAnalysis(path=record.path, index=global_idx, is_raw=record.is_raw, error=True)
            finally:
                exe.shutdown(wait=False)
        else:
            ans.index = global_idx

        record.thumb_ai = None
        analyses.append(ans)
        records.append(record)

        if (i+1) % 50 == 0:
            print(f"      ... {i+1}/{len(batch_records)} in {time.time()-t_ana:.2f}s so far")

    print(f"    Analysis done in {time.time()-t_ana:.2f}s. Total records: {len(records)}")

print(f"\n=== COMPLETE: {len(records)} records, {errors} errors ===")
conn.close()
