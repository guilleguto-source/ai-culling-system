"""
vlm_stream_runner.py — Ejecuta evaluación con Ollama (llama3.2-vision) de forma progresiva
sobre las carpetas que ya han sido procesadas por Stage 2.
"""
import json
import time
import logging
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.vlm_refiner import decide_winner, OLLAMA_URL
from services.analysis_store import init_store, load_analysis
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [VLM Stream] %(message)s")
log = logging.getLogger("vlm_stream")

OUT_DIR = Path(__file__).parent / "out"
RESULTS_FILE = OUT_DIR / "vlm_results.json"

def check_ollama():
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except:
        return False

def run_vlm_stream():
    log.info("Iniciando runner progresivo de Ollama (llama3.2-vision)...")
    
    if not check_ollama():
        log.error("Ollama no responde en http://localhost:11434. Asegúrate de ejecutar 'ollama serve'.")
        return

    scope_path = OUT_DIR / "scope.json"
    if not scope_path.exists():
        log.error("No se encontró scope.json.")
        return

    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    all_paths = [p for label in ("positive", "negative", "unreviewed") for p in scope[label]]
    
    por_carpeta = defaultdict(list)
    for p in all_paths:
        por_carpeta[str(Path(p).parent)].append(p)

    vlm_results = {}
    if RESULTS_FILE.exists():
        try:
            vlm_results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        except:
            vlm_results = {}

    log.info("Carpetas a monitorear: %d. Evaluaciones VLM ya completadas: %d", len(por_carpeta), len(vlm_results))

    evaluados = 0
    for carpeta, paths in por_carpeta.items():
        # Verificar si esta carpeta tiene análisis completados en SQLite
        conn = init_store(carpeta)
        
        # Buscar pares dudosos / ráfagas (fotos con score alto y cercano)
        # Para cada ráfaga con fotos parejas, tomar top 2 o 3
        fotos_analizadas = []
        import os
        for p in paths:
            try:
                mt = os.path.getmtime(p)
                ans = load_analysis(conn, p, mt)
                if ans:
                    fotos_analizadas.append((p, ans.aesthetic_score, ans.closed_eyes_count))
            except OSError:
                continue
                
        if len(fotos_analizadas) < 2:
            continue
            
        # Ordenar por estética y filtrar fotos sin ojos cerrados
        limpias = [f for f in fotos_analizadas if f[2] == 0]
        if len(limpias) < 2:
            limpias = fotos_analizadas
            
        limpias.sort(key=lambda x: x[1], reverse=True)
        top_candidates = [x[0] for x in limpias[:3]]
        
        # Clave única para este desempate
        pair_key = "|".join(sorted(top_candidates))
        if pair_key in vlm_results:
            continue  # Ya evaluado por VLM anteriormente

        # Invocar Ollama
        winner_idx = decide_winner(top_candidates)
        if winner_idx is not None:
            vlm_results[pair_key] = {
                "candidates": top_candidates,
                "winner": top_candidates[winner_idx],
                "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            evaluados += 1
            log.info("VLM Desempate [%d fotos en carpeta %s] -> Ganó: %s", 
                     len(top_candidates), Path(carpeta).name, Path(top_candidates[winner_idx]).name)
            
            # Guardar avances periódicamente
            if evaluados % 5 == 0:
                RESULTS_FILE.write_text(json.dumps(vlm_results, indent=2, ensure_ascii=False), encoding="utf-8")

    RESULTS_FILE.write_text(json.dumps(vlm_results, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Ronda de VLM completada. Total evaluados por Ollama: %d", len(vlm_results))

if __name__ == "__main__":
    while True:
        try:
            run_vlm_stream()
        except Exception as e:
            log.error("Error en vlm_stream: %s", e)
        time.sleep(60)
