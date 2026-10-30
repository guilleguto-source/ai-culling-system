"""
Pruebas automatizadas para el agrupador de ráfagas y selección de Top Pick.
"""

from cull_lab.culling.clustering import BurstClusterer, PhotoMetadata


def test_temporal_clustering_splits_gaps():
    """Verifica que disparos rápidos se agrupen y pausas mayores a 2s dividan ráfagas."""
    clusterer = BurstClusterer(max_time_gap=2.0)

    photos = [
        # Ráfaga 1: 3 fotos con diferencia de 0.2s
        PhotoMetadata(id="P1", file_path="P1.CR3", timestamp=100.0, focus_score=8.0),
        PhotoMetadata(id="P2", file_path="P2.CR3", timestamp=100.2, focus_score=9.2),
        PhotoMetadata(id="P3", file_path="P3.CR3", timestamp=100.4, focus_score=8.5),
        # Salto temporal de 10 segundos
        # Ráfaga 2: 2 fotos
        PhotoMetadata(id="P4", file_path="P4.CR3", timestamp=110.4, focus_score=7.0),
        PhotoMetadata(id="P5", file_path="P5.CR3", timestamp=111.0, focus_score=6.5),
    ]

    clusters = clusterer.cluster_photos(photos)
    assert len(clusters) == 2

    # Cluster 1
    c1 = clusters[0]
    assert len(c1.photos) == 3
    assert c1.top_pick_id == "P2"  # Foco 9.2 es el más alto
    assert c1.classifications["P2"].is_top_pick is True
    assert c1.classifications["P1"].is_top_pick is False

    # Cluster 2
    c2 = clusters[1]
    assert len(c2.photos) == 2
    assert c2.top_pick_id == "P4"


def test_top_pick_and_alternate_classification():
    """Verifica que fotos similares de alta calidad se marquen como alternas y las peores como duplicados."""
    clusterer = BurstClusterer(max_time_gap=2.0)

    photos = [
        PhotoMetadata(id="P1", file_path="P1.JPG", timestamp=10.0, focus_score=9.5, eye_score=1.0),
        PhotoMetadata(id="P2", file_path="P2.JPG", timestamp=10.2, focus_score=9.2, eye_score=0.9),  # Alta calidad -> alternate
        PhotoMetadata(id="P3", file_path="P3.JPG", timestamp=10.4, focus_score=4.0, eye_score=0.2),  # Baja calidad -> duplicate
    ]

    clusters = clusterer.cluster_photos(photos)
    assert len(clusters) == 1
    c = clusters[0]

    assert c.top_pick_id == "P1"
    assert c.classifications["P1"].is_top_pick is True
    assert c.classifications["P2"].is_alternate is True
    assert c.classifications["P3"].is_duplicate is True


def test_visual_embedding_split():
    """Verifica que un giro brusco de cámara (baja similitud coseno) divida la ráfaga a pesar del tiempo."""
    clusterer = BurstClusterer(max_time_gap=2.0, visual_similarity_thresh=0.80)

    # Dos vectores ortogonales (similitud 0.0) disparados con 0.1s de diferencia
    v_escena_a = [1.0, 0.0, 0.0, 0.0]
    v_escena_b = [0.0, 1.0, 0.0, 0.0]

    photos = [
        PhotoMetadata(id="P1", file_path="P1.CR3", timestamp=20.0, embedding=v_escena_a),
        PhotoMetadata(id="P2", file_path="P2.CR3", timestamp=20.1, embedding=v_escena_b),
    ]

    clusters = clusterer.cluster_photos(photos)
    assert len(clusters) == 2
    assert clusters[0].photos[0].id == "P1"
    assert clusters[1].photos[0].id == "P2"


if __name__ == "__main__":
    test_temporal_clustering_splits_gaps()
    test_top_pick_and_alternate_classification()
    test_visual_embedding_split()
    print("¡Todas las pruebas de clustering pasaron exitosamente!")
