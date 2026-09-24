import urllib.request, json, sys

sys.stdout.reconfigure(encoding='utf-8')

req = urllib.request.urlopen('http://127.0.0.1:8000/results')
data = json.loads(req.read().decode('utf-8'))
results = data.get('results', [])

total = len(results)
by_label = {}
reasons_count = {}

for r in results:
    l = r.get('label', 'none')
    by_label[l] = by_label.get(l, 0) + 1
    for reas in r.get('reasons', []):
        reasons_count[reas] = reasons_count.get(reas, 0) + 1

print(f"==================================================")
print(f"   RESUMEN DE SELECCION GUTO FLOW 2.0 (2026-08-09)")
print(f"==================================================")
print(f"Total fotografías procesadas: {total}")
print(f"\n[Desglose por Etiquetas]")
labels_order = ['highlighted', 'selected', 'recommended', 'duplicates', 'closed_eyes', 'blurry']
for l in labels_order:
    c = by_label.get(l, 0)
    pct = (c / total) * 100
    print(f"  * {l.upper():<12}: {c:>3} fotos ({pct:>5.1f}%)")

sel = by_label.get('selected', 0)
high = by_label.get('highlighted', 0)
rec = by_label.get('recommended', 0)
dup = by_label.get('duplicates', 0)
eye = by_label.get('closed_eyes', 0)
blur = by_label.get('blurry', 0)

selected_total = sel + high
total_useful = selected_total + rec

print(f"\n[Métricas Clave]")
print(f"  - Selección Principal (Elegidas + Destacadas): {selected_total} fotos ({selected_total/total*100:.1f}%) [Modo 'few': ~30% - 35%]")
print(f"  - Cobertura de Personas (Recomendadas):       {rec} fotos ({rec/total*100:.1f}%)")
print(f"  - TOTAL ENTREGABLE FINAL:                      {total_useful} fotos ({total_useful/total*100:.1f}%)")
print(f"  - TOTAL DESCARTADAS:                          {total - total_useful} fotos ({(total - total_useful)/total*100:.1f}%)")
print(f"    ├─ Duplicadas en ráfaga: {dup} ({dup/total*100:.1f}%)")
print(f"    ├─ Ojos cerrados / expresiones: {eye} ({eye/total*100:.1f}%)")
print(f"    └─ Desenfoque severo: {blur} ({blur/total*100:.1f}%)")

print(f"\n[Criterios y Justificaciones Más Frecuentes]")
for reas, c in sorted(reasons_count.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  - {reas}: {c} fotos")
