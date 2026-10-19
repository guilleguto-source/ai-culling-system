# Plan de Implementación: Culling Jerárquico Centrado en VIPs, Mirada y Sonrisa

## 1. Alcance y Objetivos
Optimizar el motor de selección automática (*Culling*) de GutoFlow para:
1. **Relevancia Asimétrica de VIPs en Ráfagas:** En fotos grupales y de pareja, los protagonistas (novios, quinceañera, homenajeado, identificados por ArcFace) tienen prioridad absoluta. Si los VIPs miran a cámara y sonríen, la foto gana la ráfaga aunque un invitado secundario al fondo pestañee.
2. **Detección Biométrica de Mirada (Eye Gaze Vector):** Medir el centrado del iris respecto a las comisuras del ojo mediante los 478 landmarks faciales para determinar contacto visual real con la lente.
3. **Detección Real de Sonrisa:** Medir la elevación de comisuras labiales y exposición de dientes (aislamiento de esmalte) reemplazando el valor fijo `smile: False`.

---

## 2. Arquitectura de Decisión y Flujo de Datos

```
[478 Landmarks MediaPipe + Máscara Dientes]
   ├── Centro de Iris (468, 473) vs Contornos Oculares ──> Vector de Mirada (Gaze Deviation)
   ├── Elevación de Comisuras (61, 291) + Dientes ────────> Score de Sonrisa (0.0 - 1.0)
   └── Apertura Palpebral (EAR 3D) ───────────────────────> Ojos Abiertos / Parpadeo
           │
           ▼
[Población en PhotoAnalysis.face_attrs]
   └── {valid, ear, blink, smile, gaze_out, gaze_score, is_vip, identity_id}
           │
           ▼
[Cluster Gates & Desempate de Ráfagas (cluster_gates.py & decision.py)]
   ├── Regla 1 (Filtro Duro VIP): Si en la ráfaga hay fotos con el VIP mirando y sonriendo,
   │                              se descartan aquellas donde el VIP parpadea o mira fuera.
   ├── Regla 2 (Inmunidad Secundaria): Defectos en invitados no-VIP NO descartan la foto
   │                                   si el VIP está perfecto.
   └── Regla 3 (Score de Coherencia): Entre tomas con VIP perfecto, desempata el % de
                                      invitados secundarios atentos a cámara.
```

---

## 3. Árbol de Archivos Afectados
```
backend/services/
  ├── face_assessment.py   [Añadir: compute_iris_gaze y compute_smile_metrics con MediaPipe]
  ├── analysis.py          [Actualizar: poblar smile real, gaze_score y enlace de identidad VIP]
  ├── cluster_gates.py     [Modificar: ponderación asimétrica VIP (peso x4.0) e inmunidad secundaria]
  └── decision.py          [Actualizar: scoring de ráfaga y motivos legibles de selección VIP]
```

---

## 4. Checklist de Validación
- [x] Implementar cálculo de vector de mirada (iris vs contorno palpebral) en `face_assessment.py`.
- [x] Implementar métrica de sonrisa combinando apertura labial y dientes en `face_assessment.py`.
- [x] Conectar identidades VIP de ArcFace (`rank_vip_identities`) con `cluster_gates.py` y `culling.py`.
- [x] Implementar regla condicional de relajación de sonrisa para niños de 2-5 años o VIPs serios (`vip_smile_relaxed`).
- [x] Crear suite de pruebas en `test_vip_culling.py` (4/4 tests pasando, 23/23 tests totales de culling pasando en 2.3s).
