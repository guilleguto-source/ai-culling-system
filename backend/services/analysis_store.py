import sqlite3
import json
import hashlib
from pathlib import Path
from dataclasses import asdict
from typing import Optional
import os

from services.analysis import PhotoAnalysis

# v3: se añaden closed_eyes_count / face_count (conteo, no solo el booleano)
ANALYSIS_VERSION = 3

# Anclado al módulo, NO al cwd (ver nota en thumbnail_store.py).
ANALYSIS_DIR = Path(__file__).parent.parent / "models" / "analysis"


def _get_db_path(directory: str) -> Path:
    # Hash the directory to create a unique db file
    dir_hash = hashlib.md5(directory.encode('utf-8')).hexdigest()
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    return ANALYSIS_DIR / f"{dir_hash}.db"

def init_store(directory: str) -> sqlite3.Connection:
    db_path = _get_db_path(directory)
    conn = sqlite3.connect(str(db_path))
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
            phash TEXT,
            exif_datetime TEXT,
            blur_score REAL,
            blur_flag BOOLEAN,
            sharp_anywhere REAL,
            aesthetic_score REAL,
            saliency_region TEXT,
            pre_skin_lum REAL,
            pre_global_lum REAL,
            pre_clip_frac REAL,
            pre_wb TEXT,
            error TEXT
        )
    """)
    conn.commit()
    return conn

def load_analysis(conn: sqlite3.Connection, path: str, current_mtime: float) -> Optional[PhotoAnalysis]:
    cursor = conn.execute("SELECT * FROM photo_analysis WHERE path = ?", (path,))
    row = cursor.fetchone()
    if not row:
        return None
    
    col_names = [description[0] for description in cursor.description]
    data = dict(zip(col_names, row))
    
    if data["version"] != ANALYSIS_VERSION or data["mtime"] != current_mtime:
        return None
        
    return PhotoAnalysis(
        index=data["index_val"],
        path=data["path"],
        scene_type=data["scene_type"],
        face_bboxes=json.loads(data["face_bboxes"]) if data["face_bboxes"] else [],
        eye_landmarks=json.loads(data["eye_landmarks"]) if data["eye_landmarks"] else [],
        face_sharpness=json.loads(data["face_sharpness"]) if data["face_sharpness"] else [],
        any_closed_eyes=bool(data["any_closed_eyes"]),
        closed_eyes_count=data["closed_eyes_count"] or 0,
        face_count=data["face_count"] or 0,
        phash=data["phash"] if data["phash"] else "",
        exif_datetime=data["exif_datetime"] if data["exif_datetime"] else "",
        blur_score=data["blur_score"],
        blur_flag=bool(data["blur_flag"]),
        sharp_anywhere=data["sharp_anywhere"],
        aesthetic_score=data["aesthetic_score"],
        saliency_region=json.loads(data["saliency_region"]) if data["saliency_region"] else None,
        pre_skin_lum=data["pre_skin_lum"],
        pre_global_lum=data["pre_global_lum"],
        pre_clip_frac=data["pre_clip_frac"],
        pre_wb=tuple(json.loads(data["pre_wb"])) if data["pre_wb"] else None,
        error=data["error"] if data["error"] else ""
    )

def save_analysis(conn: sqlite3.Connection, analysis: PhotoAnalysis, mtime: float):
    conn.execute("""
        INSERT OR REPLACE INTO photo_analysis (
            path, mtime, version, index_val, scene_type, face_bboxes, eye_landmarks,
            face_sharpness, any_closed_eyes, closed_eyes_count, face_count, phash, exif_datetime,
            blur_score, blur_flag, sharp_anywhere,
            aesthetic_score, saliency_region, pre_skin_lum, pre_global_lum, pre_clip_frac, pre_wb, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        analysis.phash,
        analysis.exif_datetime,
        analysis.blur_score,
        analysis.blur_flag,
        analysis.sharp_anywhere,
        analysis.aesthetic_score,
        json.dumps(analysis.saliency_region) if analysis.saliency_region else None,
        analysis.pre_skin_lum,
        analysis.pre_global_lum,
        analysis.pre_clip_frac,
        json.dumps(analysis.pre_wb) if analysis.pre_wb else None,
        analysis.error
    ))
    conn.commit()
