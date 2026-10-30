import json
from pathlib import Path

BASELINE_FILE = Path(r"cull_lab\experiments\gutoflow3_baseline_giler.json")
USER_LR_FILE = Path(r"cull_lab\experiments\user_lightroom_giler.json")
CULLLAB_FILE = Path(r"cull_lab\experiments\cull_lab_harmonized_giler.json")

def load_data():
    with open(BASELINE_FILE, "r", encoding="utf-8") as f:
        gf3 = {Path(k).stem: v for k, v in json.load(f).items()}
    with open(USER_LR_FILE, "r", encoding="utf-8") as f:
        user = {Path(k).stem: v for k, v in json.load(f).items()}
    with open(CULLLAB_FILE, "r", encoding="utf-8") as f:
        cull = {Path(k).stem: v for k, v in json.load(f).items()}
    return gf3, user, cull

def compute_metrics(pred_set: set, truth_set: set, total_universe: int):
    tp = len(pred_set & truth_set)
    fp = len(pred_set - truth_set)
    fn = len(truth_set - pred_set)
    tn = total_universe - tp - fp - fn

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / total_universe if total_universe > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision * 100.0,
        "recall": recall * 100.0,
        "f1": f1 * 100.0,
        "accuracy": accuracy * 100.0,
    }

def main():
    if not (BASELINE_FILE.exists() and USER_LR_FILE.exists() and CULLLAB_FILE.exists()):
        print("Faltan archivos requeridos para la triangulacion.")
        return

    gf3_data, user_data, cull_data = load_data()
    all_names = set(user_data.keys())
    total_photos = len(all_names)

    # 1. Definir Conjuntos de Usuario (Truth)
    # Seleccionadas: Rating >= 2 o Pick == 1 (o Rating >= 1)
    user_sel_strict = {n for n, d in user_data.items() if d["pick"] == 1 or d["rating"] >= 2}
    user_sel_all = {n for n, d in user_data.items() if d["rating"] >= 1 or d["pick"] == 1}
    user_heroes_3s = {n for n, d in user_data.items() if d["rating"] >= 3}
    user_rej = {n for n, d in user_data.items() if d["pick"] == -1}

    # 2. Definir Conjuntos GutoFlow 3 Beta
    gf3_sel = {n for n, d in gf3_data.items() if d["rating"] >= 2 or d.get("pick") == 1}
    gf3_heroes_3s = {n for n, d in gf3_data.items() if d["rating"] >= 3}
    gf3_rej = {n for n, d in gf3_data.items() if d.get("pick") == -1}

    # 3. Definir Conjuntos CullLab Armonizado
    cull_sel = {n for n, d in cull_data.items() if d.get("is_selected", False)}
    cull_heroes_3s = {n for n, d in cull_data.items() if d["rating"] >= 3}
    cull_rej = {n for n, d in cull_data.items() if d["pick"] == -1}

    # Métricas contra la Selección Humana
    m_gf3_sel = compute_metrics(gf3_sel, user_sel_strict, total_photos)
    m_cull_sel = compute_metrics(cull_sel, user_sel_strict, total_photos)

    m_gf3_heroes = compute_metrics(gf3_heroes_3s, user_heroes_3s, total_photos)
    m_cull_heroes = compute_metrics(cull_heroes_3s, user_heroes_3s, total_photos)

    m_gf3_rej = compute_metrics(gf3_rej, user_rej, total_photos)
    m_cull_rej = compute_metrics(cull_rej, user_rej, total_photos)

    print("================================================================================")
    print("           REPORTE OFICIAL DE TRIANGULACIÓN (GILER - 842 FOTOS)                 ")
    print("================================================================================")
    print(f"Fotógrafo Humano (Lightroom):")
    print(f"  - Total Seleccionadas (>= 2* o Pick=1): {len(user_sel_strict)} fotos")
    print(f"  - Total con Estrellas (>= 1*):          {len(user_sel_all)} fotos")
    print(f"  - Fotos Cumbre (3* / Azul):             {len(user_heroes_3s)} fotos")
    print(f"  - Fotos Rechazadas (Pick=-1 / Rojo):    {len(user_rej)} fotos")
    print("--------------------------------------------------------------------------------")
    print(f"GutoFlow 3 Beta:")
    print(f"  - Total Seleccionadas: {len(gf3_sel)} | 3*: {len(gf3_heroes_3s)} | Rechazadas: {len(gf3_rej)}")
    print(f"CullLab Armonizado (Nuevo):")
    print(f"  - Total Seleccionadas: {len(cull_sel)} | 3*: {len(cull_heroes_3s)} | Rechazadas: {len(cull_rej)}")
    print("================================================================================")
    print("COMPARATIVA DE COINCIDENCIA CON EL FOTÓGRAFO (HUMAN GROUND TRUTH):")
    print("--------------------------------------------------------------------------------")
    print(f"1. SELECCIÓN GLOBAL (Aprobadas para entrega):")
    print(f"   [GutoFlow 3 Beta]       Coincidencias (TP): {m_gf3_sel['tp']:3d} / {len(user_sel_strict)} "
          f"| Precision: {m_gf3_sel['precision']:5.1f}% | Recall: {m_gf3_sel['recall']:5.1f}% | F1: {m_gf3_sel['f1']:5.1f}%")
    print(f"   [CullLab Armonizado]    Coincidencias (TP): {m_cull_sel['tp']:3d} / {len(user_sel_strict)} "
          f"| Precision: {m_cull_sel['precision']:5.1f}% | Recall: {m_cull_sel['recall']:5.1f}% | F1: {m_cull_sel['f1']:5.1f}%")
    
    delta_tp = m_cull_sel['tp'] - m_gf3_sel['tp']
    delta_f1 = m_cull_sel['f1'] - m_gf3_sel['f1']
    print(f"   >>> Impacto CullLab: {'+' if delta_tp>=0 else ''}{delta_tp} fotos coincidentes ganadas ({'+' if delta_f1>=0 else ''}{delta_f1:.1f}% F1)")
    print("--------------------------------------------------------------------------------")
    print(f"2. FOTOS CUMBRE (3* / Portafolio VIP):")
    print(f"   [GutoFlow 3 Beta]       Coincidencias (TP): {m_gf3_heroes['tp']:3d} / {len(user_heroes_3s)} "
          f"| Precision: {m_gf3_heroes['precision']:5.1f}% | Recall: {m_gf3_heroes['recall']:5.1f}%")
    print(f"   [CullLab Armonizado]    Coincidencias (TP): {m_cull_heroes['tp']:3d} / {len(user_heroes_3s)} "
          f"| Precision: {m_cull_heroes['precision']:5.1f}% | Recall: {m_cull_heroes['recall']:5.1f}%")
    print("--------------------------------------------------------------------------------")
    print(f"3. FOTOS RECHAZADAS (Descarte técnico / Rojo):")
    print(f"   [GutoFlow 3 Beta]       Coincidencias (TP): {m_gf3_rej['tp']:3d} / {len(user_rej)} "
          f"| Precision: {m_gf3_rej['precision']:5.1f}% | Recall: {m_gf3_rej['recall']:5.1f}%")
    print(f"   [CullLab Armonizado]    Coincidencias (TP): {m_cull_rej['tp']:3d} / {len(user_rej)} "
          f"| Precision: {m_cull_rej['precision']:5.1f}% | Recall: {m_cull_rej['recall']:5.1f}%")
    print("================================================================================")

    # Coincidencia directa entre GutoFlow 3 y CullLab
    cull_gf3_overlap = len(cull_sel & gf3_sel)
    print(f"Coincidencia interna entre GutoFlow 3 Beta y CullLab: {cull_gf3_overlap} fotos mutuas en común "
          f"({(cull_gf3_overlap/len(gf3_sel))*100:.1f}% de la beta)")
    print("================================================================================")

if __name__ == "__main__":
    main()
