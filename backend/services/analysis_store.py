import logging
import sqlite3
import json
import hashlib
from pathlib import Path
from typing import Optional
import os
import numpy as np

from services.analysis import PhotoAnalysis

logger = logging.getLogger(__name__)

# v3: closed_eyes_count / face_count (conteo, no solo el booleano)
# v4: atributos de MediaPipe (caras válidas, mirada, sonrisa)
# v5: face_attrs — atributos POR cara (calibración y entrenamiento)
# v6: face_attrs se mide SIEMPRE (antes dependía de detect_closed_eyes: las
#     filas v5 creadas con la casilla apagada tienen face_attrs vacío y son
#     inservibles para la calibración).
from services.app_paths import get_analysis_dir as _get_analysis_dir

# v8: Motor Estético 7-ejes + Ponderación VIP de rostros.
# v9: Rescate Tonal IA (tonal_adjustments) altas luces y sombras.
ANALYSIS_VERSION = 9

ANALYSIS_DIR = _get_analysis_dir()


def _get_db_path(directory: str) -> Path:
    # Hash the directory to create a unique db file
    dir_hash = hashlib.md5(directory.encode('utf-8')).hexdigest()
    _get_analysis_dir().mkdir(parents=True, exist_ok=True)
    return _get_analysis_dir() / f"{dir_hash}.db"

def _schema_columns() -> list[str]:
    """Columnas que el código espera (se derivan del propio CREATE TABLE)."""
    return [
        "path", "mtime", "version", "index_val", "scene_type", "face_bboxes",
        "eye_landmarks", "face_sharpness", "any_closed_eyes", "closed_eyes_count",
        "face_count", "valid_face_count", "looking_away_count", "smiling_count",
        "face_attrs", "face_identities", "phash", "exif_datetime", "blur_score", "blur_flag",
        "sharp_anywhere", "aesthetic_score", "aesthetic_breakdown", "saliency_region", "pre_skin_lum",
        "pre_global_lum", "pre_clip_frac", "pre_wb", "tonal_adjustments", "error",
    ]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Recrea la tabla si su esquema no coincide con el que espera el código.

    `CREATE TABLE IF NOT EXISTS` NO agrega columnas a una tabla que ya existe:
    al añadir campos nuevos, una base vieja seguía con el esquema antiguo y el
    INSERT fallaba ("no column named ..."). ANALYSIS_VERSION invalida las
    FILAS, no el ESQUEMA. Como esto es un caché, recrear es seguro: se
    regenera analizando.
    """
    existentes = [r[1] for r in conn.execute("PRAGMA table_info(photo_analysis)")]
    if not existentes:
        return                                  # tabla nueva: nada que migrar
    if set(existentes) != set(_schema_columns()):
        logger.info("Esquema de análisis desactualizado: se recrea el caché.")
        conn.execute("DROP TABLE photo_analysis")
        conn.commit()


def init_store(directory: str) -> sqlite3.Connection:
    db_path = _get_db_path(directory)
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    _ensure_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photo_analysis (
            path TEXT PRIMARY KEY,
            mtime REAL,
            version INTEGER,
            index_val INTEGER,
            scene_type TEXT,
            face_bboxes TEXT,
            eye_landmarks TEXT,
            face_sharpness TEXT,
            any_closed_eyes BOOLEAN,
            closed_eyes_count INTEGER,
            face_count INTEGER,
            valid_face_count INTEGER,
            looking_away_count INTEGER,
            smiling_count INTEGER,
            face_attrs TEXT,
            face_identities TEXT,
            phash TEXT,
            exif_datetime TEXT,
            blur_score REAL,
            blur_flag BOOLEAN,
            sharp_anywhere REAL,
            aesthetic_score REAL,
            aesthetic_breakdown TEXT,
            saliency_region TEXT,
            pre_skin_lum REAL,
            pre_global_lum REAL,
            pre_clip_frac REAL,
            pre_wb TEXT,
            tonal_adjustments TEXT,
            error TEXT
        )
    """)
    conn.commit()
    return conn

def _row_to_analysis(data: dict) -> PhotoAnalysis:
    """Reconstruye un PhotoAnalysis desde una fila del caché (dict col→valor).
    Único lugar que conoce el mapeo columnas→objeto: load_analysis y
    get_all_analysis lo comparten para no divergir."""
    face_identities_raw = json.loads(data["face_identities"]) if data.get("face_identities") else []
    face_identities = [
        np.array(e, dtype=np.float32) if e is not None else None
        for e in face_identities_raw
    ] if face_identities_raw else []

    return PhotoAnalysis(
        index=data["index_val"],
        path=data["path"],
        mtime=data["mtime"],
        scene_type=data["scene_type"],
        face_bboxes=json.loads(data["face_bboxes"]) if data["face_bboxes"] else [],
        eye_landmarks=json.loads(data["eye_landmarks"]) if data["eye_landmarks"] else [],
        face_sharpness=json.loads(data["face_sharpness"]) if data["face_sharpness"] else [],
        any_closed_eyes=bool(data["any_closed_eyes"]),
        closed_eyes_count=data["closed_eyes_count"] or 0,
        face_count=data["face_count"] or 0,
        valid_face_count=data["valid_face_count"] or 0,
        looking_away_count=data["looking_away_count"] or 0,
        smiling_count=data["smiling_count"] or 0,
        face_attrs=json.loads(data["face_attrs"]) if data["face_attrs"] else [],
        face_identities=face_identities,
        phash=data["phash"] if data["phash"] else "",
        exif_datetime=data["exif_datetime"] if data["exif_datetime"] else "",
        blur_score=data["blur_score"],
        blur_flag=bool(data["blur_flag"]),
        sharp_anywhere=data["sharp_anywhere"],
        aesthetic_score=data["aesthetic_score"],
        aesthetic_breakdown=json.loads(data["aesthetic_breakdown"]) if data.get("aesthetic_breakdown") else {},
        saliency_region=json.loads(data["saliency_region"]) if data["saliency_region"] else None,
        pre_skin_lum=data["pre_skin_lum"],
        pre_global_lum=data["pre_global_lum"],
        pre_clip_frac=data["pre_clip_frac"],
        pre_wb=tuple(json.loads(data["pre_wb"])) if data["pre_wb"] else None,
        tonal_adjustments=json.loads(data["tonal_adjustments"]) if data.get("tonal_adjustments") else {},
        error=data["error"] if data["error"] else ""
    )


def load_analysis(conn: sqlite3.Connection, path: str, current_mtime: float) -> Optional[PhotoAnalysis]:
    cursor = conn.execute("SELECT * FROM photo_analysis WHERE path = ?", (path,))
    row = cursor.fetchone()
    if not row:
        return None

    col_names = [description[0] for description in cursor.description]
    data = dict(zip(col_names, row))

    if data["version"] != ANALYSIS_VERSION or data["mtime"] != current_mtime:
        return None

    # Guardia de CONTENIDO (además de la versión): una fila con caras pero sin
    # atributos medidos es inservible para calibración/descartes. Puede pasar
    # si un backend viejo en memoria escribió con lógica anterior — el número
    # de versión no protege contra procesos desactualizados.
    if (data["face_count"] or 0) > 0 and data["face_attrs"] in (None, "", "[]"):
        from services import face_mesh
        if face_mesh.is_available():
            return None     # se re-analiza y esta vez sí se mide

    return _row_to_analysis(data)

def refresh_mtimes(conn: sqlite3.Connection, paths: list[str]) -> int:
    """
    Re-sella el análisis con el mtime actual de cada foto.

    Necesario porque el propio pipeline escribe el XMP DENTRO del JPG al
    terminar: eso cambia el mtime y el análisis recién guardado quedaba
    invalidado por su propia escritura — el caché nunca acertaba y la
    re-selección "instantánea" volvía a analizarlo todo.

    Es seguro: el XMP solo toca metadatos; los píxeles no cambian, así que el
    análisis sigue siendo válido.
    """
    n = 0
    for p in set(paths):
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        cur = conn.execute(
            "UPDATE photo_analysis SET mtime = ? WHERE path = ?", (mtime, p))
        n += cur.rowcount
    conn.commit()
    return n


def save_analysis(conn: sqlite3.Connection, analysis: PhotoAnalysis, mtime: float):
    face_identities_json = json.dumps([
        e.tolist() if isinstance(e, np.ndarray) else e
        for e in analysis.face_identities
    ]) if getattr(analysis, "face_identities", None) else None

    conn.execute("""
        INSERT OR REPLACE INTO photo_analysis (
            path, mtime, version, index_val, scene_type, face_bboxes, eye_landmarks,
            face_sharpness, any_closed_eyes, closed_eyes_count, face_count,
            valid_face_count, looking_away_count, smiling_count, face_attrs, face_identities, phash, exif_datetime,
            blur_score, blur_flag, sharp_anywhere,
            aesthetic_score, aesthetic_breakdown, saliency_region, pre_skin_lum, pre_global_lum, pre_clip_frac, pre_wb, tonal_adjustments, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        analysis.path,
        mtime,
        ANALYSIS_VERSION,
        analysis.index,
        analysis.scene_type,
        json.dumps(analysis.face_bboxes),
        json.dumps(analysis.eye_landmarks),
        json.dumps(analysis.face_sharpness),
        analysis.any_closed_eyes,
        analysis.closed_eyes_count,
        analysis.face_count,
        analysis.valid_face_count,
        analysis.looking_away_count,
        analysis.smiling_count,
        json.dumps(analysis.face_attrs),
        face_identities_json,
        analysis.phash,
        analysis.exif_datetime,
        analysis.blur_score,
        analysis.blur_flag,
        analysis.sharp_anywhere,
        analysis.aesthetic_score,
        json.dumps(getattr(analysis, "aesthetic_breakdown", {})),
        json.dumps(analysis.saliency_region) if analysis.saliency_region else None,
        analysis.pre_skin_lum,
        analysis.pre_global_lum,
        analysis.pre_clip_frac,
        json.dumps(analysis.pre_wb) if analysis.pre_wb else None,
        json.dumps(getattr(analysis, "tonal_adjustments", {})),
        analysis.error
    ))
    conn.commit()

def get_all_analysis(directory: str) -> list[PhotoAnalysis]:
    """Todo el análisis cacheado de un directorio, SIN comprobar mtime ni
    versión (lo consumen la búsqueda semántica y el storyline, que trabajan
    sobre lo ya analizado). Cada objeto trae su `mtime` para poder resolver el
    embedding cacheado sin re-stat del disco."""
    db_path = _get_db_path(directory)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT * FROM photo_analysis")
        col_names = [description[0] for description in cursor.description]
        results = []
        descartadas = 0
        for row in cursor.fetchall():
            data = dict(zip(col_names, row))
            try:
                results.append(_row_to_analysis(data))
            except Exception as e:
                descartadas += 1
                logger.warning("Fila de análisis corrupta (%s): %s",
                               data.get("path", "?"), e)
        if descartadas:
            logger.warning("get_all_analysis: %d filas corruptas descartadas de %s",
                           descartadas, directory)
        return results
    finally:
        conn.close()
