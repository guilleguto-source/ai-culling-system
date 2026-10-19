"""
compare_culling_session.py — Script de comparativa de Culling.
Compara la selección previa (XMP/Rating en disco) vs. el nuevo pipeline UniFace + SigLIP (v10).

La decisión del nuevo sistema usa el motor REAL de producción:
  cluster_images -> assign_cluster_representatives -> apply_decision_logic
con selectivity_target="few" (30%), respetando los límites del workflow real.
"""
import sys
import time
from pathlib import Path
import logging
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ingester import get_ingest_tasks, process_single_image
from services.analysis import analyze_photo
from services.xmp_reader import read_xmp
from services.clustering import cluster_images, assign_cluster_representatives, find_exact_duplicates
from services.decision import apply_decision_logic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("culling_comparator")

# ── Preferencias: cambiar SELECTIVITY_TARGET para probar distintos umbrales ──
SELECTIVITY_TARGET = "few"   # "few"=30% | "standard"=40% | "more"=50%

PREFS = {
    "selectivity_target": SELECTIVITY_TARGET,
    "detect_duplicates": True,
    "detect_highlights": True,
    "detect_blurry": True,
    "blurry_sensitivity": "moderate",
    "detect_closed_eyes": True,
    "auto_crop": "off",
    "auto_straighten": False,
}

SETTINGS = {
    "ratings_mapping": {
        "selected":     {"stars": 2, "color": "Verde",    "flag": "pick"},
        "highlighted":  {"stars": 3, "color": "Azul",     "flag": "pick"},
        "recommended":  {"stars": 1, "color": "Amarillo", "flag": "pick"},
        "blurry":       {"stars": 0, "color": "Rojo",     "flag": "reject"},
        "closed_eyes":  {"stars": 0, "color": "",         "flag": "none"},
        "duplicates":   {"stars": 0, "color": "",         "flag": "none"},
    }
}


def parse_old_xmp_decision(img_path: str) -> dict:
    xmp_data = read_xmp(img_path)
    rating, label, is_picked = 0, "", False
    if xmp_data:
        rating = xmp_data.get("stars", 0) or 0
        label  = xmp_data.get("color", "") or ""
        is_picked = rating >= 3 or label.lower() in ("pick", "green", "blue", "red", "yellow")
    return {"rating": rating, "label": label, "is_picked": is_picked}


def run_comparison(session_dir: str):
    print("=" * 70)
    print(f"  COMPARATIVA CULLING: SISTEMA VIEJO vs. UNIFACE + SIGLIP")
    print(f"  Directorio: {session_dir}")
    print(f"  Selectividad: {SELECTIVITY_TARGET.upper()} | few=30% standard=40% more=50%")
    print("=" * 70)

    target_path = Path(session_dir)
    if not target_path.exists():
        print(f"ERROR: El directorio {session_dir} no existe o no es accesible.")
        return

    print("\n[1/5] Escaneando archivos de imagen en la sesion...")
    tasks = get_ingest_tasks(session_dir)
    print(f" -> Encontradas {len(tasks)} imagenes en la sesion.")
    if not tasks:
        return

    print("\n[2/5] Inicializando motor UniFace + SigLIP (v10)...")
    from uniface import FaceAnalyzer
    face_detector = FaceAnalyzer()

    print("\n[3/5] Analizando imagenes con el nuevo pipeline...")
    start_time = time.time()
    records, analyses, old_decisions = [], [], []

    for i, t in enumerate(tasks):
        record = process_single_image(t[0], t[1]) if isinstance(t, tuple) else process_single_image(t)
        records.append(record)
        old_decisions.append(parse_old_xmp_decision(record.path))
        a = analyze_photo(
            index=i, record=record, face_detector=face_detector,
            eye_session=None, blur_threshold=100.0,
            detect_closed_eyes=True, pre_edit_enabled=True,
        )
        analyses.append(a)
        if (i + 1) % 10 == 0 or (i + 1) == len(tasks):
            elapsed = time.time() - start_time
            print(f" -> Procesadas {i+1}/{len(tasks)} ({(i+1)/elapsed:.1f} fotos/sec)", flush=True)

    elapsed_time = time.time() - start_time
    print(f"\nProcesamiento: {elapsed_time:.1f}s ({len(tasks)/elapsed_time:.1f} fotos/sec)")

    print("\n[4/5] Clustering y motor de decision real (apply_decision_logic)...")

    scores = {i: 0.5 * min(a.blur_score / 200.0, 1.0) + 0.5 * a.aesthetic_score
              for i, a in enumerate(analyses)}
    trash_flags = [a.blur_flag for a in analyses]

    clusters = cluster_images(
        [a.phash for a in analyses],
        [a.exif_datetime for a in analyses],
        [a.scene_type for a in analyses],
    )
    clusters = assign_cluster_representatives(clusters, scores, trash_flags, analyses)
    exact_dups = find_exact_duplicates(records)

    results, _, _, _ = apply_decision_logic(
        records=records, analyses=analyses, clusters=clusters,
        rep_scores=scores, trash_flags=trash_flags,
        prefs=PREFS, settings=SETTINGS, develop_by_idx={},
        all_scores=scores, exact_duplicates=exact_dups,
    )

    new_dec_by_path = {r["path"]: r.get("label") in ("selected", "highlighted") for r in results}

    print("\n[5/5] Generando reporte comparativo...")
    coincidencias, rescatadas, depuradas = 0, [], []

    for i, (record, old_dec) in enumerate(zip(records, old_decisions)):
        new_ok = new_dec_by_path.get(record.path, False)
        old_ok = old_dec["is_picked"]
        a = analyses[i]

        if old_ok == new_ok:
            coincidencias += 1
        elif not old_ok and new_ok:
            rescatadas.append({"path": record.path, "score": round(scores.get(i, 0.0), 3),
                               "motivo": "Aprobada: nitidez limpia y rostros sin ojos cerrados"})
        else:
            detalles = []
            if a.any_closed_eyes:  detalles.append(f"{a.closed_eyes_count} ojos cerrados")
            if a.blur_flag:        detalles.append("desenfoque")
            if not detalles:       detalles.append("score por debajo del umbral de seleccion")
            depuradas.append({"path": record.path, "score": round(scores.get(i, 0.0), 3),
                              "motivo": f"Rechazada: {', '.join(detalles)}"})

    total = len(tasks)
    new_sel = sum(1 for v in new_dec_by_path.values() if v)
    old_sel = sum(1 for d in old_decisions if d["is_picked"])

    print("\n" + "=" * 70)
    print("  RESULTADOS")
    print("=" * 70)
    print(f"Total fotos:                    {total}")
    print(f"Seleccionadas SISTEMA VIEJO:    {old_sel} ({old_sel/total*100:.1f}%)")
    print(f"Seleccionadas NUEVO ({SELECTIVITY_TARGET}):      {new_sel} ({new_sel/total*100:.1f}%)")
    print(f"Coincidencia exacta:            {coincidencias}/{total} ({coincidencias/total*100:.1f}%)")
    print(f"Fotos Rescatadas (Viejo=No, Nuevo=Si): {len(rescatadas)}")
    print(f"Fotos Depuradas  (Viejo=Si, Nuevo=No): {len(depuradas)}")
    print("=" * 70)

    if depuradas:
        print(f"\nFotos DEPURADAS ({len(depuradas)}):")
        for d in depuradas:
            print(f"  - {Path(d['path']).name}: {d['motivo']}")

    out_file = Path(__file__).parent / "comparison_results.json"
    out_file.write_text(json.dumps({
        "selectivity_target": SELECTIVITY_TARGET,
        "total": total, "old_selected": old_sel, "new_selected": new_sel,
        "pct_old": round(old_sel/total*100, 2), "pct_new": round(new_sel/total*100, 2),
        "coincidencias": coincidencias, "pct_coincidencia": round(coincidencias/total*100, 2),
        "rescatadas_count": len(rescatadas), "depuradas_count": len(depuradas),
        "rescatadas": rescatadas, "depuradas": depuradas,
        "elapsed_time": round(elapsed_time, 2),
    }, indent=2), encoding="utf-8")
    print(f"\nReporte guardado en: {out_file.resolve()}")


if __name__ == "__main__":
    path_arg = r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09"
    if len(sys.argv) > 1:
        path_arg = sys.argv[1]
    run_comparison(path_arg)
