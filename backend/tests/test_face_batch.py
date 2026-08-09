import numpy as np
import pytest
from services import face_identity


def test_embed_faces_batch_empty():
    res = face_identity.embed_faces_batch([])
    assert res == []


def test_embed_faces_batch_handles_invalid_data():
    # Entradas vacías o con arrays de tamaño 0
    dummy_faces = [
        (np.zeros((0, 0, 3), dtype=np.uint8), [0, 0, 10, 10], None),
        (None, [0, 0, 10, 10], None),
    ]
    res = face_identity.embed_faces_batch(dummy_faces)
    assert len(res) == 2
    assert res[0] is None
    assert res[1] is None
