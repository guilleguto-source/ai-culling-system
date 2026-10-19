"""
benchmark_v1_vs_v2.py — Enfrentamiento directo entre Sistema v1 vs Sistema v2.
"""
import sys
import sqlite3
import json
from pathlib import Path
from collections import Counter

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent / "teamwork_projects" / "ai_culling_system" / "backend"))

from services.cluster_gates import apply_technical_gates_explained, compute_vip_weights
from services.clustering import cluster_images, ImageCluster

DB_PATH = r"C:\Users\Guill\teamwork_projects\ai_culling_system\backend\models\analysis\7538f5d190047070243c054ca674a762.db"

def run_benchmark():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM photo_analysis ORDER BY index_val ASC").fetchall()
    
    print(f"Total imágenes cargadas: {len(rows)}")
    
    # Reconstruir datos para clustering
    phashes = [r["phash"] or "" for r in rows]
    scene_types = [r["scene_type"] or "detail" for r in rows]
    exif_dts = [r["exif_datetime"] or "" for r in rows]
    
    clusters = cluster_images(phashes, scene_types, exif_dts)
    print(f"Clusters / Ráfagas detectadas: {len(clusters)}")
    
    face_attrs_list = [json.loads(r["face_attrs"]) if r["face_attrs"] else [] for r in rows]
    face_sharpness_list = [json.loads(r["face_sharpness"]) if r["face_sharpness"] else [] for r in rows]
    face_bboxes_list = [json.loads(r["face_bboxes"]) if r["face_bboxes"] else [] for r in rows]
    
    # -------------------------------------------------------------
    # 1. EJECUCIÓN V1 (Gates rígidos sin VIP, Score estético 3 ejes)
    # -------------------------------------------------------------
    v1_winners = []
    v1_rejections = Counter()
    
    for c in clusters:
        indices = c.image_indices
        if not indices:
            continue
        # En V1 se pasaban los gates sin bboxes (sin VIP)
        survivors_v1, motivos_v1 = apply_technical_gates_explained(
            indices, face_attrs_list, face_sharpness_list, face_bboxes_list=None
        )
        for m in motivos_v1.values():
            v1_rejections[m] += 1
            
        # Elegir ganador en v1 según el score antiguo (primer eje / tercios básicos)
        best_v1 = max(survivors_v1, key=lambda i: rows[i]["aesthetic_score"])
        v1_winners.append(best_v1)

    # -------------------------------------------------------------
    # 2. EJECUCIÓN V2 (Gates con VIP Facial, Score estético 7 ejes)
    # -------------------------------------------------------------
    v2_winners = []
    v2_rejections = Counter()
    vip_saved_count = 0
    different_winners = 0
    
    for c in clusters:
        indices = c.image_indices
        if not indices:
            continue
        # En V2 se pasan los bboxes para calcular ponderación VIP por rostro
        survivors_v2, motivos_v2 = apply_technical_gates_explained(
            indices, face_attrs_list, face_sharpness_list, face_bboxes_list=face_bboxes_list
        )
        for m in motivos_v2.values():
            v2_rejections[m] += 1
            
        # Evaluar desglose de 7 ejes de v2
        def get_v2_overall(idx):
            bd_str = rows[idx]["aesthetic_breakdown"]
            if bd_str:
                try:
                    bd = json.loads(bd_str)
                    return bd.get("overall_score", rows[idx]["aesthetic_score"])
                except Exception:
                    pass
            return rows[idx]["aesthetic_score"]

        best_v2 = max(survivors_v2, key=lambda i: get_v2_overall(i))
        v2_winners.append(best_v2)
        
        # Comparar supervivientes y ganador
        if len(survivors_v2) > len(apply_technical_gates_explained(indices, face_attrs_list, face_sharpness_list, None)[0]):
            vip_saved_count += 1
            
        # En v1 se elegía best_v1, en v2 se elige best_v2
        if best_v1 != best_v2:
            different_winners += 1

    print("\n=======================================================")
    print("        RESULTADOS DEL ENFRENTAMIENTO: V1 vs V2")
    print("=======================================================")
    print(f"Total ráfagas evaluadas: {len(clusters)}")
    print(f"Ráfagas con ganador diferente (V1 vs V2): {different_winners} ({different_winners/max(1, len(clusters))*100:.1f}%)")
    print(f"Fotos de ráfagas salvadas del descarte por VIP (protagonista perfecto vs parpadeo fondo): {vip_saved_count}")
    print("\n--- Descarte por Gates Técnicos ---")
    print("Motivo                V1 (Rígido)    V2 (VIP & Edge-Aware)")
    for motivo in ["ojos_cerrados", "mirada_desviada", "rostro_blando"]:
        print(f"{motivo:<22} {v1_rejections[motivo]:<14} {v2_rejections[motivo]:<14}")

if __name__ == "__main__":
    run_benchmark()
