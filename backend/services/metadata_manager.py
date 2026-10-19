"""
metadata_manager.py — Gestión de perfiles de copyright, lectura GPS EXIF y armado de taxonomía.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

from PIL import Image, ExifTags

from services.app_paths import get_user_data_dir

logger = logging.getLogger(__name__)

PROFILES_FILE = "metadata_profiles.json"

# Ciudades ecuatorianas de referencia con coordenadas aproximadas (lat, lon)
ECUADOR_CITIES = {
    "Guayaquil": (-2.1894, -79.8891),
    "Samborondón": (-2.1283, -79.8290),
    "Daule": (-1.8647, -79.9775),
    "Durán": (-2.1706, -79.8222),
    "Salinas": (-2.2145, -80.9515),
    "Manta": (-0.9677, -80.7089),
    "Cuenca": (-2.9001, -79.0059),
    "Quito": (-0.1807, -78.4678),
    "Ambato": (-1.2491, -78.6168),
    "Machala": (-3.2581, -79.9554),
    "Loja": (-3.9931, -79.2042),
    "Portoviejo": (-1.0544, -80.4544),
    "Santo Domingo": (-0.2530, -79.1754),
}

# Taxonomía base de eventos y tags generales por lote
EVENT_TAXONOMY: Dict[str, Dict[str, any]] = {
    "matine": {
        "label": "Matiné / Fiesta Infantil",
        "has_age": True,
        "base_tags": ["Matiné", "Infantil", "Fiesta", "Celebración"]
    },
    "cumpleanos_dia": {
        "label": "Cumpleaños en el Día",
        "has_age": True,
        "base_tags": ["Cumpleaños", "Fiesta", "Celebración"]
    },
    "cumpleanos_noche": {
        "label": "Cumpleaños en la Noche",
        "has_age": True,
        "base_tags": ["Cumpleaños", "Noche", "Fiesta", "Celebración"]
    },
    "boda_civil_dia": {
        "label": "Boda Civil (Día)",
        "has_age": False,
        "base_tags": ["Boda Civil", "Matrimonio", "Boda", "Celebración"]
    },
    "boda_civil_farra": {
        "label": "Boda Civil y Farra",
        "has_age": False,
        "base_tags": ["Boda Civil", "Matrimonio", "Fiesta", "Celebración"]
    },
    "boda_religiosa": {
        "label": "Boda Religiosa",
        "has_age": False,
        "base_tags": ["Boda", "Matrimonio", "Ceremonia", "Recepción"]
    },
    "quinceanera": {
        "label": "Quinceañera",
        "has_age": False,
        "default_age": "15 Años",
        "base_tags": ["Quinceañera", "15 Años", "Fiesta", "Celebración"]
    },
    "aniversario": {
        "label": "Aniversario",
        "has_age": True,
        "base_tags": ["Aniversario", "Celebración", "Homenaje"]
    },
    "bautizo": {
        "label": "Bautizo",
        "has_age": False,
        "base_tags": ["Bautizo", "Ceremonia", "Familia", "Celebración"]
    },
    "primera_comunion": {
        "label": "Primera Comunión",
        "has_age": False,
        "base_tags": ["Primera Comunión", "Ceremonia", "Familia"]
    },
    "confirmacion": {
        "label": "Confirmación",
        "has_age": False,
        "base_tags": ["Confirmación", "Ceremonia", "Familia"]
    },
    "baby_shower": {
        "label": "Baby Shower",
        "has_age": False,
        "base_tags": ["Baby Shower", "Familia", "Celebración"]
    },
    "sesion_pareja": {
        "label": "Sesión de Pareja / Pre-Boda",
        "has_age": False,
        "base_tags": ["Sesión de Pareja", "Retrato", "Love Story"]
    },
    "corporativo": {
        "label": "Evento Corporativo",
        "has_age": False,
        "base_tags": ["Evento Corporativo", "Institucional", "Conferencia"]
    },
    "general": {
        "label": "Otro / General",
        "has_age": False,
        "base_tags": ["Fotografía Profesional", "Evento Social"]
    }
}


def _get_profiles_path() -> Path:
    return get_user_data_dir() / PROFILES_FILE


def get_metadata_profiles() -> List[dict]:
    """Retorna la lista de perfiles de copyright guardados."""
    p_path = _get_profiles_path()
    if not p_path.exists():
        # Crear perfil inicial por defecto
        initial_profiles = [
            {
                "id": str(uuid.uuid4()),
                "name": "Principal / Estudio",
                "creator": "Guille Guto",
                "copyright_notice": "© {year} Guille Guto. Todos los derechos reservados.",
                "credit": "Guille Guto Photography",
                "usage_terms": "Uso personal y privado acordado bajo contrato.",
                "web_statement": "https://guilleguto.com",
                "is_default": True,
            }
        ]
        save_all_profiles(initial_profiles)
        return initial_profiles

    try:
        data = json.loads(p_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as e:
        logger.error(f"Error leyendo {p_path}: {e}")

    return []


def save_all_profiles(profiles: List[dict]) -> None:
    """Guarda la lista completa de perfiles."""
    p_path = _get_profiles_path()
    p_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")


def save_or_update_profile(profile_data: dict) -> dict:
    """Crea o actualiza un perfil de copyright."""
    profiles = get_metadata_profiles()
    pid = profile_data.get("id") or str(uuid.uuid4())
    profile_data["id"] = pid

    is_default = profile_data.get("is_default", False)
    if is_default or len(profiles) == 0:
        for p in profiles:
            p["is_default"] = False
        profile_data["is_default"] = True

    updated = False
    for i, p in enumerate(profiles):
        if p.get("id") == pid:
            profiles[i] = profile_data
            updated = True
            break

    if not updated:
        profiles.append(profile_data)

    save_all_profiles(profiles)
    return profile_data


def delete_metadata_profile(profile_id: str) -> bool:
    """Elimina un perfil por ID."""
    profiles = get_metadata_profiles()
    initial_len = len(profiles)
    profiles = [p for p in profiles if p.get("id") != profile_id]

    if len(profiles) < initial_len:
        # Asegurar que al menos uno sea default si quedan perfiles
        if profiles and not any(p.get("is_default") for p in profiles):
            profiles[0]["is_default"] = True
        save_all_profiles(profiles)
        return True
    return False


def set_default_profile(profile_id: str) -> bool:
    """Establece un perfil como predeterminado."""
    profiles = get_metadata_profiles()
    found = False
    for p in profiles:
        if p.get("id") == profile_id:
            p["is_default"] = True
            found = True
        else:
            p["is_default"] = False

    if found:
        save_all_profiles(profiles)
    return found


def _dms_to_decimal(dms, ref: str) -> Optional[float]:
    """Convierte grados, minutos y segundos a valor decimal."""
    try:
        deg = float(dms[0])
        minute = float(dms[1])
        sec = float(dms[2])
        dec = deg + (minute / 60.0) + (sec / 3600.0)
        if ref in ("S", "W"):
            dec = -dec
        return dec
    except (TypeError, ValueError, IndexError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en kilómetros entre dos coordenadas geográficas."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _find_nearest_ecuador_city(lat: float, lon: float, max_dist_km: float = 35.0) -> Optional[str]:
    """Retorna la ciudad ecuatoriana más cercana si se encuentra dentro de max_dist_km."""
    closest_city = None
    min_dist = float("inf")
    for city, (c_lat, c_lon) in ECUADOR_CITIES.items():
        d = _haversine_km(lat, lon, c_lat, c_lon)
        if d < min_dist:
            min_dist = d
            closest_city = city

    if min_dist <= max_dist_km:
        return closest_city
    return None


def extract_gps_from_file(image_path: Path) -> Optional[Tuple[float, float]]:
    """Extrae latitud y longitud decimales de un archivo JPEG/TIFF/DNG si contiene EXIF GPS."""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None
            
            # GPSInfo está en el tag 34853 (0x8825)
            gps_ifd = exif.get_ifd(0x8825)
            if not gps_ifd:
                return None

            lat_dms = gps_ifd.get(2)  # GPSLatitude
            lat_ref = gps_ifd.get(1)  # GPSLatitudeRef
            lon_dms = gps_ifd.get(4)  # GPSLongitude
            lon_ref = gps_ifd.get(3)  # GPSLongitudeRef

            if lat_dms and lat_ref and lon_dms and lon_ref:
                lat = _dms_to_decimal(lat_dms, lat_ref)
                lon = _dms_to_decimal(lon_dms, lon_ref)
                if lat is not None and lon is not None:
                    return lat, lon
    except Exception:
        pass
    return None


def inspect_file_metadata(image_path: Path) -> dict:
    """Extrae metadatos actuales del archivo (EXIF o XMP sidecar si existe)."""
    result = {
        "creator": None,
        "copyright": None,
        "gps": None
    }
    # 1. Buscar XMP sidecar primero
    xmp_sidecar = image_path.with_suffix(".xmp")
    if not xmp_sidecar.exists():
        xmp_sidecar = image_path.with_name(f"{image_path.name}.xmp")

    if xmp_sidecar.exists():
        try:
            from lxml import etree
            root = etree.parse(str(xmp_sidecar)).getroot()
            namespaces = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
            }
            creators = root.xpath("//dc:creator/rdf:Seq/rdf:li/text()", namespaces=namespaces)
            if creators:
                result["creator"] = str(creators[0]).strip()
            rights = root.xpath("//dc:rights/rdf:Alt/rdf:li/text()", namespaces=namespaces)
            if rights:
                result["copyright"] = str(rights[0]).strip()
        except Exception:
            pass

    # 2. Si no hay en XMP, leer de EXIF (para JPG/DNG/TIFF)
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif:
                if not result["creator"] and exif.get(0x013B):  # Artist
                    result["creator"] = str(exif.get(0x013B)).strip()
                if not result["copyright"] and exif.get(0x8298):  # Copyright
                    result["copyright"] = str(exif.get(0x8298)).strip()
    except Exception:
        pass

    result["gps"] = extract_gps_from_file(image_path)
    return result


def detect_gps_in_directory(directory_path: str, max_files_to_check: int = 25) -> dict:
    """
    Escanea imágenes en la carpeta en busca de coordenadas GPS EXIF y metadatos existentes.
    Retorna si se encontró GPS, coordenadas, la ciudad más cercana y los metadatos actuales.
    """
    p = Path(directory_path)
    if not p.exists() or not p.is_dir():
        return {
            "has_gps": False,
            "latitude": None,
            "longitude": None,
            "suggested_city": None,
            "existing_creator": None,
            "existing_copyright": None,
            "sample_file": None
        }

    valid_exts = {".jpg", ".jpeg", ".dng", ".tif", ".tiff", ".arw", ".cr2", ".cr3", ".nef"}
    checked = 0
    found_gps = None
    existing_creator = None
    existing_copyright = None
    sample_file = None

    for f in p.glob("*"):
        if f.is_file() and f.suffix.lower() in valid_exts:
            checked += 1
            info = inspect_file_metadata(f)
            if not sample_file:
                sample_file = f.name
            if not existing_creator and info.get("creator"):
                existing_creator = info.get("creator")
            if not existing_copyright and info.get("copyright"):
                existing_copyright = info.get("copyright")

            if info.get("gps") and not found_gps:
                found_gps = info.get("gps")
                sample_file = f.name

            if (found_gps and existing_creator and existing_copyright) or checked >= max_files_to_check:
                break

    lat, lon = (found_gps if found_gps else (None, None))
    city = _find_nearest_ecuador_city(lat, lon) if (lat is not None and lon is not None) else None

    return {
        "has_gps": found_gps is not None,
        "latitude": round(lat, 5) if lat is not None else None,
        "longitude": round(lon, 5) if lon is not None else None,
        "suggested_city": city,
        "existing_creator": existing_creator,
        "existing_copyright": existing_copyright,
        "sample_file": sample_file
    }


def build_batch_metadata_payload(
    profile: dict,
    event_type: str,
    age: Optional[str],
    protagonist: Optional[str],
    city: Optional[str],
    custom_tags_str: Optional[str],
    year: Optional[int] = None
) -> dict:
    """
    Genera el diccionario de metadatos estandarizados a inyectar en XMP.
    Sustituye variables dinámicas ({year}, {client}, {creator}) y consolida palabras clave.
    """
    if year is None:
        year = datetime.now().year

    creator = profile.get("creator", "").strip()
    notice_tmpl = profile.get("copyright_notice", "© {year} {creator}").strip()
    client_name = (protagonist or "").strip()

    # Reemplazo de comodines dinámicos
    copyright_notice = (
        notice_tmpl
        .replace("{year}", str(year))
        .replace("{creator}", creator)
        .replace("{client}", client_name)
    )

    # Armado de Keywords (Tags) generales por lote
    keywords = []
    seen = set()

    def add_tag(tag: str):
        t = tag.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            keywords.append(t)

    # 1. Tags base del tipo de evento
    event_info = EVENT_TAXONOMY.get(event_type)
    if event_info:
        for t in event_info.get("base_tags", []):
            add_tag(t)
        if event_info.get("default_age") and not age:
            add_tag(event_info["default_age"])

    # 2. Edad / Años
    if age and age.strip():
        clean_age = age.strip()
        if not clean_age.lower().endswith("años") and not clean_age.lower().endswith("año"):
            clean_age = f"{clean_age} Años"
        add_tag(clean_age)

    # 3. Protagonistas
    if client_name:
        add_tag(client_name)

    # 4. Ciudad
    if city and city.strip():
        add_tag(city.strip())

    # 5. Tags manuales libres separados por comas
    if custom_tags_str:
        for raw in custom_tags_str.split(","):
            add_tag(raw)

    title = client_name if client_name else (event_info["label"] if event_info else "")

    return {
        "creator": creator,
        "copyright": copyright_notice,
        "credit": profile.get("credit", "").strip(),
        "usage_terms": profile.get("usage_terms", "").strip(),
        "web_statement": profile.get("web_statement", "").strip(),
        "title": title,
        "city": (city or "").strip(),
        "country": "Ecuador" if (city and city.strip() in ECUADOR_CITIES) else "",
        "keywords": keywords,
    }
