"""
fase_q_experiment.py — Experimento Fase Q: pares con hermanas en 0★ +
señales faciales continuas (ear/blink/smile/gaze_out/yaw) vs. binarizadas.

No toca taste_model ni history.db en modo lectura (stage1/stage3/stage4);
solo stage2 escribe (analysis_store por carpeta + caché de embeddings CLIP,
ambos cachés normales de la app, reutilizables después por el culling real).

Uso:
    python scripts/fase_q_experiment.py stage1                 # gratis, solo lectura
    python scripts/fase_q_experiment.py stage2 --scope scope.json   # pesado
    python scripts/fase_q_experiment.py stage3 --scope scope.json   # arma A/B/C
    python scripts/fase_q_experiment.py stage4                  # GroupKFold + tabla
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # backend/ en el path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fase_q")

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

BURST_GAP_S = 30          # mismo criterio temporal que history_taste.py
BURST_SIM = 0.90          # idem, para el corte fino con embeddings reales
MAX_LOSERS_PER_WINNER = 3


def _ts(valor: str):
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# --- Stage 1: alcance real, solo lectura de history.db --------------------

def stage1(args):
    from services.history_store import HistoryStore

    store = HistoryStore()
    rows = store.rows_for_bursts()  # (path, label, capture_time)
    por_carpeta = defaultdict(list)
    for path, label, capture in rows:
        por_carpeta[str(Path(path).parent)].append((path, label, _ts(capture)))

    # Ráfagas PROVISORIAS por tiempo solamente (sin embeddings todavía) —
    # sobre-incluyen un poco; el corte fino real ocurre en build_burst_pairs
    # una vez que stage2 haya calculado los embeddings CLIP verdaderos.
    candidatos_por_label = defaultdict(set)
    n_rafagas_revisadas = 0
    for carpeta, items in por_carpeta.items():
        items.sort(key=lambda x: (x[2] is None, x[2]))
        rafaga: list[tuple] = []

        def cerrar(rafaga):
            nonlocal n_rafagas_revisadas
            if any(l == "positive" for _, l, _ in rafaga):
                n_rafagas_revisadas += 1
                for p, l, _ in rafaga:
                    if l in ("positive", "negative", "unreviewed"):
                        candidatos_por_label[l].add(p)

        prev_ts = None
        for path, label, ts in items:
            if rafaga and prev_ts and ts and (ts - prev_ts).total_seconds() <= BURST_GAP_S:
                rafaga.append((path, label, ts))
            else:
                cerrar(rafaga)
                rafaga = [(path, label, ts)]
            prev_ts = ts
        cerrar(rafaga)

    scope = {
        "positive": sorted(candidatos_por_label["positive"]),
        "negative": sorted(candidatos_por_label["negative"]),
        "unreviewed": sorted(candidatos_por_label["unreviewed"]),
    }
    out_path = OUT_DIR / "scope.json"
    out_path.write_text(json.dumps(scope, indent=2), encoding="utf-8")

    total_historia = store.count()
    log.info("Filas en history.db: %d", total_historia)
    log.info("Ráfagas provisorias con >=1 positiva: %d", n_rafagas_revisadas)
    for label, paths in scope.items():
        log.info("  %-12s %d fotos", label, len(paths))
    log.info("Guardado: %s", out_path)
    log.info(
        "Nota: 'unreviewed' aquí es la novedad de Fase Q — hoy esas fotos no "
        "tienen embedding CLIP ni face_attrs. Eso es lo que hace stage2."
    )


# --- Stage 2: analizar + embeber el scope (pesado, escribe caché) ---------

def _cargar_modelos():
    import cv2
    models_dir = Path(__file__).parent.parent / "models"
    face_detector = None
    yunet_path = models_dir / "yunet.onnx"
    if yunet_path.exists():
        face_detector = cv2.FaceDetectorYN.create(
            str(yunet_path), "", (320, 320),
            score_threshold=0.6, nms_threshold=0.3, top_k=5000,
        )
    eye_session = None
    eye_path = models_dir / "eye_state.onnx"
    if eye_path.exists():
        import onnxruntime as ort
        eye_session = ort.InferenceSession(str(eye_path), providers=["CPUExecutionProvider"])
    return face_detector, eye_session


def stage2(args):
    from services.ingester import process_single_image
    from services.analysis import analyze_photo
    from services.analysis_store import init_store, load_analysis, save_analysis
    from services.settings_manager import get_blur_threshold, load_settings
    from services import embedding_service
    import os

    scope = json.loads(Path(args.scope).read_text(encoding="utf-8"))
    all_paths = [p for label in ("positive", "negative", "unreviewed") for p in scope[label]]
    log.info("Fotos a procesar (analysis + embedding): %d", len(all_paths))

    face_detector, eye_session = _cargar_modelos()
    settings = load_settings()
    blur_threshold = get_blur_threshold(settings)

    por_carpeta = defaultdict(list)
    for p in all_paths:
        por_carpeta[str(Path(p).parent)].append(p)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    analysis_lock = threading.Lock()

    def _procesar_foto(path_str: str, conn):
        nonlocal ya_cacheadas, errores
        try:
            mtime = os.path.getmtime(path_str)
        except OSError:
            return None, True  # error
            
        with analysis_lock:
            ans = load_analysis(conn, path_str, mtime)

        if ans is None:
            rec = process_single_image(Path(path_str))
            if rec.error:
                return None, True
            with analysis_lock:
                ans = analyze_photo(
                    index=0, record=rec, face_detector=face_detector,
                    eye_session=eye_session, blur_threshold=blur_threshold,
                    detect_closed_eyes=True, pre_edit_enabled=False,
                )
                save_analysis(conn, ans, mtime)
            pixels = rec.thumb_ai
        else:
            pixels = None

        if embedding_service.embed_path(path_str, pixels) is None and pixels is None:
            rec = process_single_image(Path(path_str))
            if not rec.error:
                embedding_service.embed_path(path_str, rec.thumb_ai)

        return path_str, False

    t0 = time.time()
    hechas = errores = ya_cacheadas = 0
    BATCH_SIZE = 16

    for carpeta, paths in por_carpeta.items():
        conn = init_store(carpeta)
        for i in range(0, len(paths), BATCH_SIZE):
            batch = paths[i:i + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(_procesar_foto, p, conn) for p in batch]
                for future in as_completed(futures):
                    res, err = future.result()
                    if err:
                        errores += 1
                    else:
                        hechas += 1

                    if hechas > 0 and hechas % 200 == 0:
                        dt = time.time() - t0
                        log.info("%d/%d (%.1f/s) — cacheadas antes: %d, errores: %d",
                                  hechas, len(all_paths), hechas / dt, ya_cacheadas, errores)

    log.info("Listo. %d procesadas, %d ya estaban cacheadas, %d errores. %.1f min.",
              hechas, ya_cacheadas, errores, (time.time() - t0) / 60)


# --- Stage 3: construir conjuntos A / B / C por PAR --------------------

def _agg_continuo(face_attrs: list[dict]) -> dict:
    """'La peor cara del grupo' — misma filosofía que min(sharps) en producción."""
    validas = [a for a in face_attrs if a.get("valid")]
    if not validas:
        return {"min_ear": 1.0, "max_blink": 0.0, "mean_smile": 0.0,
                "max_gaze_out": 0.0, "max_abs_yaw": 0.0}
    return {
        "min_ear": min(a["ear"] for a in validas),
        "max_blink": max(a["blink"] for a in validas),
        "mean_smile": sum(a["smile"] for a in validas) / len(validas),
        "max_gaze_out": max(a["gaze_out"] for a in validas),
        "max_abs_yaw": max(abs(a["yaw"]) for a in validas),
    }


def _features_foto(path: str) -> dict | None:
    """Set A (binarizado, ya en producción) + Set B (continuo) para una foto,
    leyendo del analysis_store de su carpeta sin requerir que el NAS esté montado."""
    from services.analysis_store import init_store
    import json

    norm_path = str(Path(path))
    carpeta = str(Path(path).parent)
    conn = init_store(carpeta)
    cursor = conn.execute("SELECT * FROM photo_analysis WHERE path = ? OR path = ?", (norm_path, path))
    row = cursor.fetchone()
    if not row:
        return None
    col_names = [description[0] for description in cursor.description]
    data = dict(zip(col_names, row))
    if data.get("version") != 6:
        return None

    face_sharp = json.loads(data["face_sharpness"]) if data.get("face_sharpness") else []
    face_attrs = json.loads(data["face_attrs"]) if data.get("face_attrs") else []
    cont = _agg_continuo(face_attrs)
    return {
        "path": path,
        # --- A: actual en producción ---
        "closed_eyes_count": data.get("closed_eyes_count") or 0,
        "looking_away_count": data.get("looking_away_count") or 0,
        "smiling_count": data.get("smiling_count") or 0,
        "blur_score": data.get("blur_score") or 0.0,
        "sharp_anywhere": data.get("sharp_anywhere") or 0.0,
        "aesthetic_score": data.get("aesthetic_score") or 0.0,
        # --- B: continuo, agregando la peor cara ---
        **cont,
        "face_sharp_min": min(face_sharp) if face_sharp else 0.0,
        "face_sharp_mean": (sum(face_sharp) / len(face_sharp)) if face_sharp else 0.0,
    }


def stage3(args):
    from services.history_store import HistoryStore
    from services import embedding_service

    scope = json.loads(Path(args.scope).read_text(encoding="utf-8"))
    store = HistoryStore()
    rows = store.rows_for_bursts()
    por_carpeta = defaultdict(list)
    scoped = set(scope["positive"]) | set(scope["negative"]) | set(scope["unreviewed"])
    scoped.update(str(Path(p)) for p in list(scoped))
    for path, label, capture in rows:
        if path in scoped:
            por_carpeta[str(Path(path).parent)].append((path, label, _ts(capture)))

    def misma_rafaga(emb_a, ts_a, emb_b, ts_b):
        import numpy as np
        if emb_a is None or emb_b is None:
            return False
        if ts_a and ts_b and abs((ts_b - ts_a).total_seconds()) > BURST_GAP_S:
            return False
        return float(np.dot(emb_a, emb_b)) >= BURST_SIM

    def pares_de_rafaga(rafaga):
        ganadoras = [r for r in rafaga if r[1] == "positive"]
        if not ganadoras:
            return []
        perdedoras = [r for r in rafaga if r[1] in ("negative", "unreviewed")]
        return [(g, p) for g in ganadoras for p in perdedoras[:MAX_LOSERS_PER_WINNER]]

    pares_paths: list[tuple] = []
    for carpeta, items in por_carpeta.items():
        items.sort(key=lambda x: (x[2] is None, x[2]))
        rafaga, prev_emb, prev_ts = [], None, None
        for path, label, ts in items:
            emb = embedding_service.embed_path(path, None)
            if emb is None:
                continue
            if rafaga and misma_rafaga(prev_emb, prev_ts, emb, ts):
                rafaga.append((path, label, emb))
            else:
                pares_paths.extend(pares_de_rafaga(rafaga))
                rafaga = [(path, label, emb)]
            prev_emb, prev_ts = emb, ts
        pares_paths.extend(pares_de_rafaga(rafaga))

    log.info("Pares reconstruidos con embeddings reales: %d", len(pares_paths))

    registros = []
    faltantes = 0
    for (gpath, glabel, gemb), (ppath, plabel, pemb) in pares_paths:
        fg, fp = _features_foto(gpath), _features_foto(ppath)
        if fg is None or fp is None:
            faltantes += 1
            continue
        registros.append({
            "cluster": str(Path(gpath).parent),
            "winner": fg, "loser": fp,
            "loser_label": plabel,   # 'negative' o 'unreviewed' — para desglosar el resultado
            "winner_emb": gemb.tolist(), "loser_emb": pemb.tolist(),
        })

    out = OUT_DIR / "pares_features.json"
    out.write_text(json.dumps(registros), encoding="utf-8")
    log.info("Pares con features completas: %d (faltantes: %d)", len(registros), faltantes)
    log.info("  de los cuales perdedora=negative: %d, perdedora=unreviewed(0★): %d",
              sum(1 for r in registros if r["loser_label"] == "negative"),
              sum(1 for r in registros if r["loser_label"] == "unreviewed"))
    log.info("Guardado: %s", out)


# --- Stage 4: GroupKFold, conjuntos A / B / C ------------------------------

FEATS_A = ["closed_eyes_count", "looking_away_count", "smiling_count",
           "blur_score", "sharp_anywhere", "aesthetic_score"]
FEATS_B = ["min_ear", "max_blink", "mean_smile", "max_gaze_out", "max_abs_yaw",
           "face_sharp_min", "face_sharp_mean"]
FEATS_C = FEATS_A + FEATS_B


def stage4(args):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    registros = json.loads((OUT_DIR / "pares_features.json").read_text(encoding="utf-8"))
    if len(registros) < 200:
        log.warning("Solo %d pares — con <1000 la medición es ruido (ver lección de Fase Q).",
                    len(registros))

    def matriz(feats: list[str]):
        X, y, groups = [], [], []
        rng = np.random.default_rng(0)
        for r in registros:
            w, l = r["winner"], r["loser"]
            wv = np.array([w[f] for f in feats], dtype=np.float64)
            lv = np.array([l[f] for f in feats], dtype=np.float64)
            # orden aleatorio para no sesgar (el modelo no debe aprender "el primero gana")
            if rng.random() < 0.5:
                X.append(wv - lv); y.append(1)
            else:
                X.append(lv - wv); y.append(0)
            groups.append(r["cluster"])
        return np.array(X), np.array(y), np.array(groups)

    def evaluar(feats: list[str], nombre: str):
        X, y, groups = matriz(feats)
        n_grupos = len(set(groups))
        gkf = GroupKFold(n_splits=min(5, n_grupos))
        aciertos = []
        for tr, te in gkf.split(X, y, groups):
            sc = StandardScaler().fit(X[tr])
            clf = LogisticRegression(max_iter=1000).fit(sc.transform(X[tr]), y[tr])
            aciertos.append(clf.score(sc.transform(X[te]), y[te]))
        m, s = float(np.mean(aciertos)), float(np.std(aciertos))
        log.info("%-12s acierto = %.1f%% (±%.1f) sobre %d pares, %d ráfagas",
                  nombre, m * 100, s * 100, len(y), n_grupos)
        return m, s

    log.info("=== Fase Q extendida: A (actual) vs B (continuo) vs C (ambos) ===")
    evaluar(FEATS_A, "A - actual")
    evaluar(FEATS_B, "B - continuo")
    evaluar(FEATS_C, "C - ambos")
    log.info("Regla: con este tamaño de muestra, diferencias <~3 puntos no son concluyentes.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="stage", required=True)

    s1 = sub.add_parser("stage1")
    s1.set_defaults(func=stage1)

    s2 = sub.add_parser("stage2")
    s2.add_argument("--scope", default=str(OUT_DIR / "scope.json"))
    s2.set_defaults(func=stage2)

    s3 = sub.add_parser("stage3")
    s3.add_argument("--scope", default=str(OUT_DIR / "scope.json"))
    s3.set_defaults(func=stage3)

    s4 = sub.add_parser("stage4")
    s4.set_defaults(func=stage4)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
