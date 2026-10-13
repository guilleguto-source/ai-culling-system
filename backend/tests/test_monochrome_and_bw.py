import numpy as np
import pytest

from services.bw_recommender import compute_bw_recommendation
from services.technical_quality import analyze_sharpness, evaluate_blur
from services.clustering import cluster_images


def test_bw_recommender_asymmetric_channel_clipping():
    # Simula una imagen donde el canal Rojo está quemado (>245),
    # pero Verde y Azul tienen textura intacta
    h, w = 100, 100
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :, 0] = 250  # Rojo saturado
    img[:, :, 1] = 60   # Verde medio
    img[:, :, 2] = 40   # Azul bajo

    is_cand, score, reasons = compute_bw_recommendation(img)
    assert score > 0.4
    assert any("altas luces" in r or "monocromática" in r for r in reasons)


def test_bw_recommender_high_contrast_candles():
    # Simula imagen con fondo muy oscuro y velas / rostro brillante
    h, w = 100, 100
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # 85% sombras profundas
    img[:85, :] = 10
    # 15% luces altas puntuales (velas)
    img[85:, :] = 240

    is_cand, score, reasons = compute_bw_recommendation(img)
    assert score >= 0.25
    assert any("contraste tonal" in r.lower() or "claroscuro" in r.lower() for r in reasons)


def test_monochrome_red_sharpness_not_crushed():
    # Escena roja pura con bordes nítidos de textura en el canal rojo
    h, w = 100, 100
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Patrón alternado de alta frecuencia en el canal rojo (R=240 vs R=30)
    img[:, ::2, 0] = 240
    img[:, 1::2, 0] = 30
    img[:, :, 1] = 20  # Verde bajo
    img[:, :, 2] = 10  # Azul bajo

    # Con la detección monocromática, no se aplasta el canal rojo
    score, label = analyze_sharpness(img, None, "full", use_fft=False)
    assert score > 500.0  # Nitidez fuerte preservada


def test_clustering_prevents_merging_different_face_counts():
    # 2 fotos tomadas con 0.5s de diferencia pero una es retrato individual (1 cara)
    # y la otra es retrato doble (2 caras)
    phashes = ["a1b2c3d4e5f60000", "a1b2c3d4e5f60000"]
    timestamps = ["2026-09-29 18:00:00", "2026-09-29 18:00:01"]
    scene_types = ["portrait", "portrait"]
    face_counts = [1, 2]

    clusters = cluster_images(
        phashes=phashes,
        exif_datetimes=timestamps,
        scene_types=scene_types,
        face_counts=face_counts,
    )
    # Deben quedar en 2 clusters separados, NO fusionadas en un solo duplicado
    assert len(clusters) == 2
