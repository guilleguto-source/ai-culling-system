"""
hardware_profiler.py — Diagnóstico y Auto-Tuning de Hardware para Guto Flow.
Detecta CPU, RAM y GPU (CUDA/MPS) y genera una recomendación de rendimiento óptima.
Guarda los resultados en caché para evitar re-análisis innecesarios en cada arranque (máx 90 días).
"""
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

CACHE_EXPIRY_DAYS = 90

def get_hardware_profile(force_rescan: bool = False) -> Dict[str, Any]:
    """
    Obtiene el perfil de hardware del sistema.
    Si existe un perfil en settings.json y tiene menos de 90 días, lo reutiliza.
    """
    from services.settings_manager import get_settings, save_settings
    
    settings = get_settings()
    cached = settings.get("hardware_profile")
    
    if cached and not force_rescan:
        last_scan_str = cached.get("last_scan")
        if last_scan_str:
            try:
                last_scan = datetime.fromisoformat(last_scan_str)
                if datetime.now() - last_scan < timedelta(days=CACHE_EXPIRY_DAYS):
                    return cached
            except Exception as e:
                logger.warning(f"Error parseando fecha de hardware_profile: {e}")
                
    profile = scan_hardware()
    
    # Persistir en settings
    settings["hardware_profile"] = profile
    save_settings(settings)
    
    return profile


def scan_hardware() -> Dict[str, Any]:
    """
    Ejecuta un análisis exhaustivo del hardware actual.
    """
    import psutil
    
    # 1. CPU & RAM
    cpu_physical = psutil.cpu_count(logical=False) or 2
    cpu_logical = psutil.cpu_count(logical=True) or 4
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    
    # 2. GPU Detection
    has_cuda = False
    has_mps = False
    gpu_name = "None"
    vram_gb = 0.0
    
    try:
        import torch
        if torch.cuda.is_available():
            has_cuda = True
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 1)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            has_mps = True
            gpu_name = "Apple Silicon GPU (MPS)"
            vram_gb = ram_gb  # Unified memory
    except Exception as e:
        logger.warning(f"Error verificando GPU con PyTorch: {e}")

    # 3. Clasificación de Tier y Recomendaciones
    if has_cuda and vram_gb >= 7.5 and ram_gb >= 15.0:
        tier = "ultra"
        tier_label = "Ultra (Alto Rendimiento GPU)"
        use_cascade = True
        heavy_detector = "scrfd_10g"
        safety_cap = 0.40
        max_workers = min(cpu_logical, 12)
        description = f"GPU potente detectada ({gpu_name}, {vram_gb}GB VRAM). Cascada 2-Pass activa a máxima velocidad."
    elif (has_cuda and vram_gb >= 3.5) or has_mps or (ram_gb >= 15.0 and cpu_physical >= 6):
        tier = "balanced"
        tier_label = "Balanceado (GPU Media / CPU Potente)"
        use_cascade = True
        heavy_detector = "scrfd_10g"
        safety_cap = 0.25
        max_workers = min(cpu_physical, 6)
        description = f"Hardware balanceado ({gpu_name if (has_cuda or has_mps) else 'CPU ' + str(cpu_physical) + ' núcleos'}). Cascada activa con liberación de memoria."
    elif ram_gb >= 7.5 and cpu_physical >= 4:
        tier = "cpu_light"
        tier_label = "CPU Estándar"
        use_cascade = True
        heavy_detector = "scrfd_10g"
        safety_cap = 0.15
        max_workers = max(1, cpu_physical - 1)
        description = "Sin GPU dedicada. Cascada 2-Pass activa con límite estricto del 15% para no sobrecargar el procesador."
    else:
        tier = "low_spec"
        tier_label = "Bajo Consumo / Recursos Limitados"
        use_cascade = False
        heavy_detector = "scrfd_500m"
        safety_cap = 0.0
        max_workers = 2
        description = "Recursos limitados. Se usará exclusivamente el modelo ligero (SCRFD-500M) para garantizar fluidez."

    return {
        "tier": tier,
        "tier_label": tier_label,
        "description": description,
        "specs": {
            "has_gpu": has_cuda or has_mps,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb,
            "cpu_physical_cores": cpu_physical,
            "cpu_logical_threads": cpu_logical,
            "ram_gb": ram_gb
        },
        "recommended_config": {
            "use_cascade": use_cascade,
            "heavy_detector": heavy_detector,
            "safety_cap": safety_cap,
            "max_workers": max_workers
        },
        "last_scan": datetime.now().isoformat()
    }
