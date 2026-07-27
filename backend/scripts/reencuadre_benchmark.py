"""
reencuadre_benchmark.py — ¿El auto-crop se parece a cómo recorta el usuario?

Ground truth: CropLeft/Top/Right/Bottom del historial de Lightroom (rectángulo
retenido, fracciones 0..1). Se compara contra propose_crop alimentado con las
caras/saliencia/escena YA cacheadas en el análisis local (no toca el NAS).

Métricas:
  - Cuánto recorta el usuario de verdad (área retenida).
  - IoU entre el rectángulo propuesto y el real.
  - Acuerdo binario "¿recortar o no?" (el usuario recorta si retiene <97% del área).
  - IoU vs baseline "no recortar" (marco completo) — si el auto-crop no supera
    al marco completo, estorba.

Uso:  python scripts/reencuadre_benchmark.py [--level medio]
"""
import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reencuadre")

DB = Path(__file__).parent.parent / "models" / "history.db"
OUT = Path(__file__).parent / "out" / "reencuadre_benchmark.json"


def _iou(a, b):
    """IoU de dos rectángulos (l, t, r, b) en fracciones."""
    il = max(a[0], b[0]); it = max(a[1], b[1])
    ir = min(a[2], b[2]); ib = min(a[3], b[3])
    if ir <= il or ib <= it:
        return 0.0
    inter = (ir - il) * (ib - it)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="medio")
    args = ap.parse_args()

    from services.auto_crop import propose_crop
    from services.analysis_store import _get_db_path

    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT path, crop FROM history WHERE crop != '' AND crop != '{}'").fetchall()

    # rectángulo real del usuario por path (case original para el hash del DB)
    reales = {}
    for path, crop in rows:
        try:
            d = json.loads(crop)
        except json.JSONDecodeError:
            continue
        l = float(d.get("CropLeft", 0.0) or 0.0)
        t = float(d.get("CropTop", 0.0) or 0.0)
        r = float(d.get("CropRight", 1.0) or 1.0)
        b = float(d.get("CropBottom", 1.0) or 1.0)
        if r > l and b > t:
            reales[str(Path(path))] = (l, t, r, b)

    por_carpeta = defaultdict(list)
    for p in reales:
        por_carpeta[str(Path(p).parent)].append(p)

    resultados = []
    procesadas = sin_analisis = 0
    for carpeta, paths in por_carpeta.items():
        db = _get_db_path(carpeta)
        if not db.exists():
            continue
        c2 = sqlite3.connect(str(db))
        tabla = {r[0]: r[1:] for r in c2.execute(
            "SELECT path, face_bboxes, eye_landmarks, saliency_region, "
            "scene_type FROM photo_analysis WHERE version=6")}
        c2.close()

        for p in paths:
            fila = tabla.get(p)
            if fila is None:
                sin_analisis += 1
                continue
            fb_j, el_j, sal_j, stype = fila
            face_bboxes = json.loads(fb_j) if fb_j else []
            eye_lm = json.loads(el_j) if el_j else []
            sal = tuple(json.loads(sal_j)) if sal_j else None

            # img_shape: no está cacheado; propose_crop usa fracciones, así que
            # un shape de referencia (thumb AI ~1600) sirve para las proporciones.
            prop = propose_crop(
                scene_type=stype or "detail", face_bboxes=face_bboxes,
                eye_landmarks=eye_lm, saliency_region=sal,
                img_shape=(1067, 1600), level=args.level, horizon_angle=None)

            real = reales[p]
            area_real = (real[2] - real[0]) * (real[3] - real[1])
            if prop is None:
                prop_rect = (0.0, 0.0, 1.0, 1.0)   # el sistema NO recorta
                prop_recorta = False
            else:
                prop_rect = (prop.left, prop.top, prop.right, prop.bottom)
                prop_recorta = prop.crop_amount > 0.02

            resultados.append({
                "path": p,
                "area_real": round(float(area_real), 4),
                "user_recorta": bool(area_real < 0.97),
                "prop_recorta": bool(prop_recorta),
                "iou_prop": round(_iou(prop_rect, real), 4),
                "iou_fullframe": round(_iou((0.0, 0.0, 1.0, 1.0), real), 4),
            })
            procesadas += 1
        if procesadas and procesadas % 2000 == 0:
            log.info("%d procesadas — sin_análisis %d", procesadas, sin_analisis)

    OUT.write_text(json.dumps(resultados), encoding="utf-8")
    log.info("Guardado %s (%d filas, %d sin análisis)", OUT, len(resultados), sin_analisis)

    # --- resumen ---
    r = resultados
    n = len(r)
    if not n:
        log.warning("sin datos"); return

    user_c = np.array([x["user_recorta"] for x in r])
    prop_c = np.array([x["prop_recorta"] for x in r])
    areas = np.array([x["area_real"] for x in r])
    iou_p = np.array([x["iou_prop"] for x in r])
    iou_f = np.array([x["iou_fullframe"] for x in r])

    log.info("=== REENCUADRE (nivel %s), n=%d ===", args.level, n)
    log.info("El usuario recorta (retiene <97%%) en %.0f%% de las fotos con crop",
             user_c.mean() * 100)
    log.info("  área retenida cuando recorta: mediana %.2f, p10 %.2f",
             float(np.median(areas[user_c])) if user_c.any() else 0,
             float(np.percentile(areas[user_c], 10)) if user_c.any() else 0)
    acuerdo = (user_c == prop_c).mean() * 100
    log.info("Acuerdo binario recortar/no: %.0f%%  (el sistema propone recorte en %.0f%%)",
             acuerdo, prop_c.mean() * 100)
    log.info("IoU medio propuesta vs real:        %.3f", iou_p.mean())
    log.info("IoU medio 'marco completo' vs real: %.3f", iou_f.mean())
    log.info("→ el auto-crop %s al marco completo",
             "SUPERA" if iou_p.mean() > iou_f.mean() else "PIERDE contra")
    # sólo donde el usuario SÍ recortó (el caso que importa)
    if user_c.any():
        log.info("  solo donde el usuario recortó: IoU prop %.3f vs marco %.3f",
                 iou_p[user_c].mean(), iou_f[user_c].mean())


if __name__ == "__main__":
    main()
