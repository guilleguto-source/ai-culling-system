"""
vlm_pair_benchmark.py — ¿El VLM rompe el techo de ~60% de las señales
geométricas en la tarea de pares de Fase Q?

Evalúa decide_winner (collage 2 paneles) sobre una muestra de los pares con
veredicto real del fotógrafo (pares_features.json). La posición de la ganadora
se sortea por par (seed fija) para anular el sesgo de posición.

Reanudable: los veredictos se agregan línea a línea en out/vlm_benchmark.jsonl;
re-correr salta lo ya evaluado. Solo usa thumbs locales — no necesita el NAS.

Uso:  python scripts/vlm_pair_benchmark.py [--n 1000]
"""
import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vlm_bench")

OUT_DIR = Path(__file__).parent / "out"
PARES = OUT_DIR / "pares_features.json"
RESULTADOS = OUT_DIR / "vlm_benchmark.jsonl"


def pair_id(w: str, l: str) -> str:
    return f"{w}||{l}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    args = ap.parse_args()

    from services.vlm_refiner import decide_winner, _model_name
    from services.thumbnail_store import read_thumbnail_from_disk

    log.info("Modelo: %s", _model_name())

    regs = json.loads(PARES.read_text(encoding="utf-8"))
    log.info("Pares totales: %d", len(regs))

    rng = random.Random(42)
    muestra = rng.sample(regs, min(args.n, len(regs)))

    hechos = set()
    if RESULTADOS.exists():
        for line in RESULTADOS.read_text(encoding="utf-8").splitlines():
            try:
                hechos.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    log.info("Ya evaluados: %d", len(hechos))

    aciertos = fallos = sin_thumb = sin_veredicto = 0
    t0 = time.time()
    with RESULTADOS.open("a", encoding="utf-8") as out:
        for k, r in enumerate(muestra):
            w, l = r["winner"]["path"], r["loser"]["path"]
            pid = pair_id(w, l)
            if pid in hechos:
                continue
            if not (read_thumbnail_from_disk(w, "duel") and read_thumbnail_from_disk(l, "duel")):
                sin_thumb += 1
                continue

            # posición de la ganadora sorteada por par (determinista por id)
            pos_w = random.Random(pid).randint(0, 1)
            candidatas = [w, l] if pos_w == 0 else [l, w]

            idx = decide_winner(candidatas)
            registro = {
                "id": pid, "loser_label": r["loser_label"],
                "cluster": r["cluster"], "pos_winner": pos_w, "vlm_idx": idx,
            }
            if idx is None:
                sin_veredicto += 1
                registro["correcto"] = None
            else:
                correcto = (idx == pos_w)
                registro["correcto"] = correcto
                aciertos += int(correcto)
                fallos += int(not correcto)
            out.write(json.dumps(registro) + "\n")
            out.flush()

            evaluados = aciertos + fallos
            if evaluados and evaluados % 25 == 0:
                acc = aciertos / evaluados * 100
                rate = evaluados / (time.time() - t0)
                log.info("%d evaluados — acierto %.1f%% — %.2f pares/s — sin_thumb %d, sin_veredicto %d",
                         evaluados, acc, rate, sin_thumb, sin_veredicto)

    evaluados = aciertos + fallos
    log.info("Listo. evaluados=%d aciertos=%d (%.1f%%) sin_thumb=%d sin_veredicto=%d",
             evaluados, aciertos, (aciertos / evaluados * 100) if evaluados else 0.0,
             sin_thumb, sin_veredicto)


if __name__ == "__main__":
    main()
