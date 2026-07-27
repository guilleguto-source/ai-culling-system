"""
enderezado_benchmark.py — ¿Cuánto le erra detect_horizon_angle al criterio
real del fotógrafo?

Ground truth: CropAngle del historial de Lightroom (history.db) — los ángulos
que el usuario aplicó A MANO. 8.664 fotos con ángulo real (>0.05°) + control
de fotos que él dejó SIN rotar (las falsas correcciones son el peor error:
Fase K mostró que endereza selectivamente, no siempre).

Corre sobre los thumbs 'duel' cacheados en disco local — no necesita el NAS.
Convención de signos: CropAngle de Lightroom es horario-negativo; se compara
también el signo invertido y se reporta la orientación que mejor concuerde.

Uso:  python scripts/enderezado_benchmark.py
Salida: out/enderezado_benchmark.json + resumen por consola.
"""
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("enderezado")

OUT = Path(__file__).parent / "out" / "enderezado_benchmark.json"
DB = Path(__file__).parent.parent / "models" / "history.db"


def main():
    from services.auto_crop import detect_horizon_angle
    from services.thumbnail_store import read_thumbnail_from_disk

    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT path, crop FROM history WHERE crop != '' AND crop != '{}'").fetchall()

    casos = []           # (path, angulo_usuario)
    for path, crop in rows:
        try:
            d = json.loads(crop)
        except json.JSONDecodeError:
            continue
        ang = float(d.get("CropAngle", 0) or 0)
        casos.append((path, ang))

    con_ang = [(p, a) for p, a in casos if abs(a) > 0.05]
    sin_ang = [(p, a) for p, a in casos if abs(a) <= 0.05]
    log.info("con ángulo: %d — sin ángulo (control): %d", len(con_ang), len(sin_ang))

    resultados = []
    t0, procesadas, sin_thumb = time.time(), 0, 0
    for path, ang_usuario in con_ang + sin_ang:
        data = read_thumbnail_from_disk(path, "duel")
        if not data:
            sin_thumb += 1
            continue
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        if arr is None:
            sin_thumb += 1
            continue
        detectado = detect_horizon_angle(arr)
        resultados.append({
            "path": path,
            "angulo_usuario": round(ang_usuario, 3),
            "detectado": round(detectado, 3) if detectado is not None else None,
        })
        procesadas += 1
        if procesadas % 1000 == 0:
            log.info("%d procesadas (%.1f/s) — sin_thumb %d",
                     procesadas, procesadas / (time.time() - t0), sin_thumb)

    OUT.write_text(json.dumps(resultados), encoding="utf-8")
    log.info("Guardado %s (%d filas, %d sin thumb)", OUT, len(resultados), sin_thumb)

    # --- resumen ---
    con = [r for r in resultados if abs(r["angulo_usuario"]) > 0.05]
    sin = [r for r in resultados if abs(r["angulo_usuario"]) <= 0.05]

    def stats(grupo, nombre):
        n = len(grupo)
        detect = [r for r in grupo if r["detectado"] is not None]
        cob = len(detect) / n * 100 if n else 0
        log.info("%s: n=%d — el detector opina en %.1f%%", nombre, n, cob)
        return detect

    d_con = stats(con, "FOTOS QUE EL USUARIO ROTÓ")
    if d_con:
        for signo, etq in [(1, "signo directo"), (-1, "signo invertido")]:
            errs = [abs(signo * r["detectado"] - r["angulo_usuario"]) for r in d_con]
            log.info("  MAE (%s): %.2f° — mediana %.2f°",
                     etq, float(np.mean(errs)), float(np.median(errs)))

    d_sin = stats(sin, "CONTROL (usuario NO rotó)")
    if d_sin:
        falsos = [r for r in d_sin if abs(r["detectado"]) > 1.0]
        log.info("  falsas correcciones >1°: %d de %d (%.1f%%) — esto es lo que 'hacía mal'",
                 len(falsos), len(d_sin), len(falsos) / len(d_sin) * 100)


if __name__ == "__main__":
    main()
