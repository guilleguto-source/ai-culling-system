"""
hardware.py — Detección automática de GPU y configuración de ONNX Runtime Execution Providers.
Soporta DirectML (Windows), CUDA, y CPU con optimización de hilos.
"""
import os
import logging
import psutil

logger = logging.getLogger(__name__)


def get_available_providers() -> list[str]:
    """
    Detecta los Execution Providers disponibles en el sistema y retorna
    la lista ordenada por prioridad: DirectML > CUDA > CPU.
    """
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        logger.info(f"ONNX Runtime providers disponibles: {available}")
        return available
    except ImportError:
        logger.error("onnxruntime no está instalado.")
        return ["CPUExecutionProvider"]


def get_optimal_providers() -> list[str]:
    """
    Retorna la lista de providers en orden de prioridad para este sistema.
    - Windows: intenta DirectML primero (funciona con AMD, Intel y NVIDIA sin CUDA).
    - Cualquier OS: intenta CUDA si está disponible.
    - Fallback universal: CPUExecutionProvider.
    """
    available = get_available_providers()
    priority_order = [
        "DmlExecutionProvider",       # DirectML — Windows (NVIDIA, AMD, Intel GPU)
        "CUDAExecutionProvider",      # CUDA — NVIDIA dedicada
        "CPUExecutionProvider",       # Fallback universal
    ]
    selected = [p for p in priority_order if p in available]
    if not selected:
        selected = ["CPUExecutionProvider"]
    logger.info(f"Providers seleccionados para inferencia: {selected}")
    return selected


def get_cpu_thread_config() -> dict:
    """
    Calcula la configuración óptima de hilos para CPUExecutionProvider
    basándose en los núcleos físicos del sistema.
    """
    physical_cores = psutil.cpu_count(logical=False) or 2
    # Usar 75% de los núcleos para inferencia, dejar margen para la UI/sistema
    inference_threads = max(1, int(physical_cores * 0.75))
    logger.info(
        f"CPU: {physical_cores} núcleos físicos → "
        f"usando {inference_threads} hilos para ONNX"
    )
    return {
        "intra_op_num_threads": inference_threads,
        "inter_op_num_threads": 1,
    }


def create_onnx_session_options():
    """
    Crea y retorna un objeto SessionOptions configurado de forma óptima
    para el hardware detectado.
    """
    import onnxruntime as ort

    providers = get_optimal_providers()
    opts = ort.SessionOptions()

    # Si solo tenemos CPU, optimizar hilos
    if providers == ["CPUExecutionProvider"]:
        thread_config = get_cpu_thread_config()
        opts.intra_op_num_threads = thread_config["intra_op_num_threads"]
        opts.inter_op_num_threads = thread_config["inter_op_num_threads"]

    # Nivel de optimización: aplicar todas las optimizaciones del grafo
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    return opts, providers


def get_hardware_info() -> dict:
    """
    Retorna información del hardware para mostrar en la UI o logs.
    """
    providers = get_optimal_providers()
    physical_cores = psutil.cpu_count(logical=False) or 0
    logical_cores = psutil.cpu_count(logical=True) or 0

    using_gpu = any(
        p in providers for p in ["DmlExecutionProvider", "CUDAExecutionProvider"]
    )
    gpu_provider = next(
        (p for p in providers if p != "CPUExecutionProvider"), None
    )

    return {
        "using_gpu": using_gpu,
        "gpu_provider": gpu_provider,
        "active_providers": providers,
        "physical_cores": physical_cores,
        "logical_cores": logical_cores,
    }
