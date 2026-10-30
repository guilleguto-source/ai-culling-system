import time
import json
import urllib.request
from pathlib import Path
from datetime import datetime

STATUS_URL = "http://127.0.0.1:8000/status"
RESULTS_URL = "http://127.0.0.1:8000/results"
OUTPUT_REPORT = Path(r"C:\Users\Guill\Desktop\GutoFlow_Benchmark_Report.json")

print("[Monitor] Iniciando escucha en http://127.0.0.1:8000/status...")

phase_timings = {}
current_phase_id = None
phase_start_time = None
phase_item_counts = {}
job_start_time = None
total_photos = 0

waiting_printed = False

while True:
    try:
        req = urllib.request.Request(STATUS_URL, headers={"User-Agent": "BenchMonitor"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        time.sleep(1.5)
        continue

    status = data.get("status")
    
    if status == "idle":
        if not waiting_printed:
            print("[Monitor] Backend en reposo (idle). Esperando a que el usuario presione 'Iniciar Culling'...")
            waiting_printed = True
        time.sleep(1.5)
        continue
    
    if status == "running":
        if job_start_time is None:
            job_start_time = time.time()
            total_photos = data.get("total", 0)
            print(f"[Monitor] !!! Culling INICIADO a las {datetime.now().strftime('%H:%M:%S')} !!!")
            print(f"[Monitor] Total fotos a procesar: {total_photos}")
            waiting_printed = False

        # Detect active phase
        active_phase = None
        for p in data.get("phases", []):
            if p.get("status") == "in_progress":
                active_phase = p
                break

        if active_phase:
            pid = active_phase.get("id")
            pname = active_phase.get("name")
            p_prog = active_phase.get("progress", 0)

            if pid != current_phase_id:
                now = time.time()
                # Close previous phase
                if current_phase_id and phase_start_time:
                    dur = now - phase_start_time
                    phase_timings[current_phase_id]["duration"] = dur
                    count = phase_timings[current_phase_id].get("items", total_photos)
                    fps = count / max(0.001, dur)
                    phase_timings[current_phase_id]["fps"] = round(fps, 2)
                    print(f"  --> Fase '{current_phase_id}' completada: {dur:.2f}s ({fps:.2f} fotos/seg)")

                # Start new phase
                current_phase_id = pid
                phase_start_time = now
                phase_timings[pid] = {
                    "name": pname,
                    "start": now,
                    "items": total_photos
                }
                print(f"[Monitor] [{datetime.now().strftime('%H:%M:%S')}] Entrando a fase: {pname} ({pid})...")

        time.sleep(1.2)

    elif status in ("complete", "finished"):
        job_end_time = time.time()
        now = job_end_time
        if current_phase_id and phase_start_time:
            dur = now - phase_start_time
            phase_timings[current_phase_id]["duration"] = dur
            count = phase_timings[current_phase_id].get("items", total_photos)
            fps = count / max(0.001, dur)
            phase_timings[current_phase_id]["fps"] = round(fps, 2)
            print(f"  --> Fase '{current_phase_id}' completada: {dur:.2f}s ({fps:.2f} fotos/seg)")

        total_elapsed = job_end_time - (job_start_time or job_end_time)
        print(f"\n[Monitor] =========================================")
        print(f"[Monitor] CULLING COMPLETADO CON ÉXITO")
        print(f"[Monitor] Tiempo total: {total_elapsed:.2f}s ({total_elapsed/60.0:.2f} min)")
        global_fps = total_photos / max(0.001, total_elapsed)
        print(f"[Monitor] Rendimiento global: {global_fps:.2f} fotos/segundo")
        print(f"[Monitor] =========================================\n")

        # Fetch results
        results_data = {}
        try:
            with urllib.request.urlopen(RESULTS_URL, timeout=5) as r_resp:
                results_data = json.loads(r_resp.read().decode("utf-8"))
        except Exception:
            pass

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_photos": total_photos,
            "total_elapsed_seconds": round(total_elapsed, 2),
            "global_fps": round(global_fps, 2),
            "phases": phase_timings,
            "backend_stats": data.get("stats", {}),
            "results_summary": {
                "selected_count": len(results_data.get("selected", [])),
                "rejected_count": len(results_data.get("rejected", [])),
                "highlighted_count": len(results_data.get("highlighted", [])),
                "total_clusters": len(results_data.get("clusters", []))
            }
        }

        with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[Monitor] Reporte detallado guardado en: {OUTPUT_REPORT}")
        break

    elif status == "error":
        print(f"[Monitor] ERROR en el job de culling: {data.get('error')}")
        break
