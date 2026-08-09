import pytest
from services.clustering import find_exact_duplicates


def test_find_exact_duplicates():
    # Hashes idénticos o casi idénticos dentro de la misma ventana de tiempo
    base_hash = "ffff0000aaaa5555"
    similar_hash = "ffff0000aaaa5554"  # 1 bit de diferencia
    different_hash = "0000ffff5555aaaa" # muchos bits de diferencia

    phashes = [base_hash, similar_hash, different_hash, base_hash]
    datetimes = [
        "2026:08:08 12:00:00",
        "2026:08:08 12:00:01",
        "2026:08:08 12:00:02",
        "2026:08:08 12:00:02",
    ]

    dups = find_exact_duplicates(phashes, datetimes, max_hamming_distance=2, max_time_gap_seconds=3.0)
    
    # El índice 1 y 3 deben ser detectados como duplicados del índice 0
    assert 1 in dups
    assert dups[1] == 0
    assert 3 in dups
    assert dups[3] == 0
    # El índice 2 es diferente, no debe ser duplicado
    assert 2 not in dups


def test_find_exact_duplicates_empty():
    assert find_exact_duplicates([]) == {}
    assert find_exact_duplicates(["ffff0000aaaa5555"]) == {}
