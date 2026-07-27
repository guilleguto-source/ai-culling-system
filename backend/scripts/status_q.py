import sys
import re
from pathlib import Path

def check_status():
    log_dir = Path(r"C:\Users\Guill\.gemini\antigravity\brain\4da1e850-8976-451e-9e87-18fe40de4d2c\.system_generated\tasks")
    logs = list(log_dir.glob("task-*.log"))
    if not logs:
        print("No hay tareas activas.")
        return
        
    # Buscar el log que contenga 'cacheadas antes' o la barra de progreso de stage2
    target_log = None
    for p in sorted(logs, key=lambda x: x.stat().st_mtime, reverse=True):
        content = p.read_text(encoding="utf-8", errors="ignore")
        if "cacheadas antes" in content:
            target_log = p
            break

    if not target_log:
        print("El análisis se está iniciando...")
        return

    lines = target_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    
    progress_lines = [l for l in lines if "INFO" in l and "/" in l and "cacheadas" in l]
    if not progress_lines:
        print("El análisis se está iniciando...")
        return
        
    last = progress_lines[-1]
    # Ejemplo: 2026-07-24 12:15:09,783 INFO 2400/85689 (0.7/s) — cacheadas antes: 0, errores: 0
    match = re.search(r"(\d+)/(\d+)\s+\(([\d.]+)/s\).*cacheadas antes:\s*(\d+),\s*errores:\s*(\d+)", last)
    if match:
        curr, total, speed, cached, errs = match.groups()
        curr, total = int(curr), int(total)
        
        # Si es la tarea reiniciada task-2839, sumar las 68,600 fotos acumuladas previas
        if "task-2839" in str(target_log) or "task-2804" in str(target_log):
            curr += 68600

        speed = float(speed)
        pct = (curr / total) * 100
        
        rem_sec = (total - curr) / speed if speed > 0 else 0
        rem_hrs = rem_sec / 3600
        
        bar_len = 30
        filled = int(bar_len * curr / total)
        bar = "#" * filled + "-" * (bar_len - filled)
        
        print("\n" + "="*50)
        print(" ESTADO DEL ANALISIS PROFUNDO (FASE Q)")
        print("="*50)
        print(f"Progreso: [{bar}] {pct:.1f}% ({curr:,} / {total:,} fotos)")
        print(f"Velocidad: {speed} fotos/segundo")
        print(f"Cacheadas reutilizadas: {cached}")
        print(f"Errores reales: {errs}")
        print(f"Tiempo restante estimado: ~{rem_hrs:.1f} horas")
        print("="*50 + "\n")
    else:
        print("Última línea registrada:", last)

if __name__ == "__main__":
    check_status()
