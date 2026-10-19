"""
utils/json_utils.py — Codificador JSON seguro para objetos NumPy y tipos nativos.
Evita errores de tipo 'Object of type bool_ is not JSON serializable'.
"""
import json
import numpy as np


class NumpySafeJSONEncoder(json.JSONEncoder):
    """Codificador JSON que serializa de manera segura primitivos y arrays de NumPy."""
    def default(self, obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def safe_dumps(obj, **kwargs) -> str:
    """Función de utilidad equivalente a json.dumps pero segura con tipos NumPy."""
    return json.dumps(obj, cls=NumpySafeJSONEncoder, **kwargs)
