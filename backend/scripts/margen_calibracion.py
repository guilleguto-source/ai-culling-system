"""
margen_calibracion.py — ¿A qué margen de score la producción empieza a errar
contra el criterio real del fotógrafo?

El VLM se dispara con margen < 0.05, un número puesto a ojo. Acá se mide, con
los 18.763 pares de Fase Q, el acierto de la fórmula fría de producción
(0.6·nitidez_norm + 0.4·estética, SHARP_REF=500) en función del margen entre
las dos candidatas — para poner el umbral donde de verdad hay duda.

Solo lee pares_features.json. Sin cómputo pesado.
"""
import json
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "out"
SHARP_REF = 500.0   # mismo valor que main.py


def score_frio(f: dict) -> float:
    return 0.6 * min(1.0, f["blur_score"] / SHARP_REF) + 0.4 * f["aesthetic_score"]


def main():
    regs = json.loads((OUT_DIR / "pares_features.json").read_text(encoding="utf-8"))
    print(f"pares: {len(regs)}")

    filas = []
    for r in regs:
        sw, sl = score_frio(r["winner"]), score_frio(r["loser"])
        margen = abs(sw - sl)
        acierta = sw > sl          # producción elige el score más alto
        filas.append((margen, acierta))

    cortes = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 1.01]
    print(f"\n{'margen':>14} {'pares':>7} {'acierto frío':>13}")
    prev = 0.0
    for c in cortes:
        bucket = [a for m, a in filas if prev <= m < c]
        if bucket:
            acc = sum(bucket) / len(bucket) * 100
            print(f"[{prev:.2f}, {c:.2f}) {len(bucket):>7} {acc:>12.1f}%")
        prev = c

    print("\nacumulado (si el VLM cubriera margen < X):")
    for c in [0.02, 0.05, 0.10, 0.15, 0.20]:
        bucket = [a for m, a in filas if m < c]
        acc = sum(bucket) / len(bucket) * 100 if bucket else 0
        frac = len(bucket) / len(filas) * 100
        print(f"  margen<{c:.2f}: {len(bucket):>6} pares ({frac:4.1f}% del total) — acierto frío {acc:.1f}%")


if __name__ == "__main__":
    main()
