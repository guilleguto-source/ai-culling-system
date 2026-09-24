/// lib.rs — Bindings PyO3 que exponen rust_core al intérprete Python.
///
/// Módulos expuestos:
///   - `extract_thumb(path)` → bytes JPEG incrustado
///   - `phash_from_bytes(bytes)` → u64
///   - `phash_batch(paths)` → list[(path, u64)]
///   - `phash_hamming(a, b)` → u32
///   - `phash_cluster(hashes, threshold)` → list[list[int]]
///   - `focus_point(path)` → (x, y, is_focused) | None

mod makernotes;
mod phash;
mod thumb_fast;

use pyo3::prelude::*;
use pyo3::types::PyBytes;

// ---------------------------------------------------------------------------
// Thumbnail extraction
// ---------------------------------------------------------------------------

#[pyfunction]
fn extract_thumb(py: Python<'_>, path: &str) -> PyResult<PyObject> {
    match thumb_fast::extract_embedded_jpeg(path) {
        Ok(bytes) => Ok(PyBytes::new_bound(py, &bytes).into()),
        Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e)),
    }
}

// ---------------------------------------------------------------------------
// pHash
// ---------------------------------------------------------------------------

#[pyfunction]
fn phash_from_bytes_py(data: &[u8]) -> PyResult<u64> {
    phash::phash_from_bytes(data).map_err(pyo3::exceptions::PyRuntimeError::new_err)
}

#[pyfunction]
fn phash_batch_py(paths: Vec<String>) -> Vec<(String, u64)> {
    phash::phash_batch(paths)
}

#[pyfunction]
fn phash_hamming(a: u64, b: u64) -> u32 {
    phash::hamming(a, b)
}

/// Agrupa hashes en clusters por similitud Hamming <= threshold.
/// Retorna lista de listas de índices (posición en el Vec original).
#[pyfunction]
fn phash_cluster(hashes: Vec<(String, u64)>, threshold: u32) -> Vec<Vec<usize>> {
    phash::cluster_by_similarity(&hashes, threshold)
}

// ---------------------------------------------------------------------------
// MakerNotes focus point & burst id
// ---------------------------------------------------------------------------

/// Extrae el punto de enfoque de un archivo RAW/JPEG.
/// Retorna (x: f32, y: f32, is_focused: bool) o None si no se puede determinar.
#[pyfunction]
fn focus_point(path: &str) -> Option<(f32, f32, bool)> {
    makernotes::extract_focus_point(path).map(|fp| (fp.x, fp.y, fp.is_focused))
}

/// Extrae el Burst ID o Sequence Number de un archivo RAW.
#[pyfunction]
fn burst_id(path: &str) -> Option<u32> {
    makernotes::extract_burst_id(path)
}

// ---------------------------------------------------------------------------
// Módulo
// ---------------------------------------------------------------------------

#[pymodule]
fn rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_thumb, m)?)?;
    m.add_function(wrap_pyfunction!(phash_from_bytes_py, m)?)?;
    m.add_function(wrap_pyfunction!(phash_batch_py, m)?)?;
    m.add_function(wrap_pyfunction!(phash_hamming, m)?)?;
    m.add_function(wrap_pyfunction!(phash_cluster, m)?)?;
    m.add_function(wrap_pyfunction!(focus_point, m)?)?;
    m.add_function(wrap_pyfunction!(burst_id, m)?)?;
    Ok(())
}
