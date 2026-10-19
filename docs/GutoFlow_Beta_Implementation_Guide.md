# 🎯 Guto Flow Beta — Manual de Implementación Completo
## Sistema de Licencias, Protección, Telemetría y Learning Automático

**Versión:** 1.0.0-beta  
**Fecha:** 2026-08-09  
**Objetivo:** Distribuir Guto Flow a colegas como blackbox, con trial de 90 días, recopilación automática de datos de aprendizaje y errores, sin exponer código ni imágenes del usuario.

---

## 📋 Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Licencias JWT con Contador Regresivo](#2-licencias-jwt-con-contador-regresivo)
3. [Protección con Nuitka (Blackbox)](#3-protección-con-nuitka-blackbox)
4. [Telemetría Automática (SQLite → Telegram)](#4-telemetría-automática-sqlite--telegram)
5. [Sentry para Errores](#5-sentry-para-errores)
6. [Learning Events (Oro para el Modelo)](#6-learning-events-oro-para-el-modelo)
7. [UI React: Consentimiento + Banner Trial](#7-ui-react-consentimiento--banner-trial)
8. [Integración en el Pipeline](#8-integración-en-el-pipeline)
9. [Configuración del Bot de Telegram](#9-configuración-del-bot-de-telegram)
10. [Script de Análisis de Datos](#10-script-de-análisis-de-datos)
11. [Flujo de Distribución](#11-flujo-de-distribución)
12. [Checklist de Implementación](#12-checklist-de-implementación)

---

## 1. Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                    GUTO FLOW DESKTOP                         │
├─────────────────────────────────────────────────────────────┤
│  Electron + React                                            │
│  ├── Banner Trial (90 días)                                 │
│  ├── Consent Dialog (primera vez)                           │
│  └── UI de Culling / Duelos / Export                       │
├─────────────────────────────────────────────────────────────┤
│  Python Backend (Nuitka compiled)                            │
│  ├── License Manager (JWT + RSA)                            │
│  ├── Telemetry System (SQLite + Telegram Bridge)            │
│  ├── Sentry SDK (errores automáticos)                       │
│  ├── Feature Extraction (single-pass)                       │
│  └── ONNX Models (empaquetados)                             │
├─────────────────────────────────────────────────────────────┤
│  LOCAL DATA LAYER                                            │
│  ├── ~/.gutoflow/license.key                                │
│  ├── ~/.gutoflow/telemetry/telemetry.db                     │
│  ├── ~/.gutoflow/telemetry/pending/*.json.gz               │
│  └── ~/.gutoflow/install.id                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   TELEGRAM BOT  │ ← Tú recibes archivos .json.gz
                    │   (automático)  │   + resúmenes de sesión
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  SENTRY.IO      │ ← Errores agrupados por release
                    │  (automático)   │
                    └─────────────────┘
```

### Principios
- **Nunca enviar imágenes, rutas reales, nombres de clientes, ni metadatos GPS.**
- **Todo es anónimo:** hashes irreversibles para fotos, IDs de instalación aleatorios.
- **Offline-first:** funciona sin internet. Los datos se acumulan y se envían cuando haya conexión.
- **No bloqueante:** si el envío falla, la app sigue funcionando perfectamente.

---

## 2. Licencias JWT con Contador Regresivo

### 2.1 Generar Par de Claves RSA (una sola vez, en TU máquina)

```bash
# En tu máquina de desarrollo, NUNCA subir private_key.pem al repo
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

### 2.2 Script para Generar Licencias (`tools/generate_license.py`)

**⚠️ Este archivo NO va en el distribuible. Solo tú lo usas.**

```python
#!/usr/bin/env python3
"""Genera licencias .gutoflow-license para testers. Corre en TU máquina."""
import jwt
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Tu clave privada (NUNCA compartir)
PRIVATE_KEY = Path("private_key.pem").read_text()

def create_license(email: str, days: int = 90, max_photos: int = 50000, tier: str = "beta"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,                           # Email del tester
        "iat": now,                             # Emitida en
        "exp": now + timedelta(days=days),      # Expira en
        "tier": tier,                           # beta | trial | pro
        "max_photos": max_photos,               # Límite de fotos
        "version": "1.0",                       # Versión de licencia
        "jti": str(hash(email + str(now))),     # ID único de token
    }

    token = jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")

    # Nombre del archivo: email seguro
    safe_email = email.replace("@", "_at_").replace(".", "_")
    filename = f"{safe_email}.gutoflow-license"
    Path(filename).write_text(token)

    print(f"✅ Licencia generada: {filename}")
    print(f"   Email: {email}")
    print(f"   Expira: {payload['exp'].strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   Días: {days}")
    print(f"   Máx fotos: {max_photos}")
    print(f"   Tier: {tier}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generate_license.py <email> [dias] [max_fotos] [tier]")
        sys.exit(1)

    email = sys.argv[1]
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    max_photos = int(sys.argv[3]) if len(sys.argv) > 3 else 50000
    tier = sys.argv[4] if len(sys.argv) > 4 else "beta"

    create_license(email, days, max_photos, tier)
```

**Uso:**
```bash
python tools/generate_license.py colega@email.com 90 50000 beta
# Genera: colega_at_email_com.gutoflow-license
```

### 2.3 License Manager en el Backend (`backend/core/license_manager.py`)

```python
"""Verificación de licencias en el binario distribuido."""
import jwt
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Clave PÚBLICA embebida en el binario (no la privada)
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
# PEGA AQUÍ EL CONTENIDO DE public_key.pem
-----END PUBLIC KEY-----"""

@dataclass
class LicenseInfo:
    user_email: str
    expires_at: datetime
    days_remaining: int
    tier: str
    max_photos: int
    is_valid: bool = True

class LicenseManager:
    def __init__(self, license_path: Path = None):
        if license_path is None:
            license_path = Path.home() / ".gutoflow" / "license.key"
        self.license_path = license_path

    def verify(self) -> LicenseInfo:
        if not self.license_path.exists():
            raise ValueError(
                "🔐 No se encontró licencia.\n"
                "Copia tu archivo .gutoflow-license en:\n"
                f"{self.license_path}"
            )

        token = self.license_path.read_text().strip()

        try:
            payload = jwt.decode(token, PUBLIC_KEY_PEM, algorithms=["RS256"])
        except jwt.ExpiredSignatureError:
            raise ValueError(
                "⏰ Tu licencia de prueba ha expirado.\n"
                "Contacta a Guto para extender tu acceso."
            )
        except jwt.InvalidTokenError:
            raise ValueError("Licencia inválida o corrupta.")

        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        days_remaining = (exp - now).days

        if days_remaining < 0:
            raise ValueError("Licencia expirada.")

        return LicenseInfo(
            user_email=payload["sub"],
            expires_at=exp,
            days_remaining=max(0, days_remaining),
            tier=payload.get("tier", "beta"),
            max_photos=payload.get("max_photos", 5000),
        )

    def check_photo_limit(self, current_count: int, license: LicenseInfo):
        if current_count > license.max_photos:
            raise ValueError(
                f"📸 Límite de fotos alcanzado ({license.max_photos}).\n"
                f"Contacta a Guto para extender tu licencia."
            )
```

### 2.4 Endpoint FastAPI para el Frontend

```python
# backend/main.py
from fastapi import FastAPI, HTTPException
from core.license_manager import LicenseManager

app = FastAPI()

@app.on_event("startup")
async def startup():
    license_mgr = LicenseManager()
    try:
        app.state.license = license_mgr.verify()
        logger.info(f"✅ Licencia válida para {app.state.license.user_email}")
        logger.info(f"⏳ Días restantes: {app.state.license.days_remaining}")
    except ValueError as e:
        logger.error(f"❌ {e}")
        raise SystemExit(1)

@app.get("/api/license/status")
def license_status():
    lic = app.state.license
    return {
        "days_remaining": lic.days_remaining,
        "user_email": lic.user_email,
        "tier": lic.tier,
        "max_photos": lic.max_photos,
        "expires_at": lic.expires_at.isoformat(),
    }
```

---

## 3. Protección con Nuitka (Blackbox)

### 3.1 Por qué Nuitka y no PyInstaller

| Herramienta | Protección | Velocidad | Tamaño | Recomendación |
|-------------|-----------|-----------|--------|---------------|
| PyInstaller | ❌ Fácil de extraer | 🟡 Media | 🟢 Compacto | No para protección |
| PyArmor | 🟡 Ofuscación | 🟡 Media | 🟢 Compacto | Capa extra opcional |
| **Nuitka** | **🟢 Compilado a C++** | **🟢 Nativo** | 🔴 Grande | **✅ Recomendado** |

Nuitka convierte Python a C++ y luego a binario nativo. Es **muy difícil** de reverse-engineer y permite empaquetar modelos ONNX dentro del ejecutable.

### 3.2 Comando de Compilación (Windows)

```bash
python -m nuitka \
  --standalone \
  --company-name="Guto Flow" \
  --product-name="Guto Flow Beta" \
  --file-version=1.0.0 \
  --product-version=1.0.0-beta \
  --windows-disable-console \
  --windows-icon-from-ico=assets/icon.ico \
  --enable-plugin=tk-inter \
  --include-package=rawpy \
  --include-package=onnxruntime \
  --include-package=fastapi \
  --include-package=uvicorn \
  --include-data-dir=backend/models=backend/models \
  --include-data-dir=frontend/dist=frontend/dist \
  --include-data-file=backend/core/public_key.pem=backend/core/public_key.pem \
  --lto=yes \
  --jobs=4 \
  backend/main.py
```

### 3.3 Comando de Compilación (macOS)

```bash
python -m nuitka \
  --standalone \
  --macos-create-app-bundle \
  --macos-disable-console \
  --macos-app-icon=assets/icon.icns \
  --include-package=rawpy \
  --include-package=onnxruntime \
  --include-data-dir=backend/models=backend/models \
  --include-data-dir=frontend/dist=frontend/dist \
  --lto=yes \
  --jobs=4 \
  backend/main.py
```

### 3.4 Estructura del Distribuible

```
GutoFlow-Beta/
├── GutoFlow.exe              # Binario Nuitka (backend + modelos)
├── runtime/                  # Dependencias (Python, DLLs, etc.)
├── frontend/
│   └── dist/                 # Build de React
├── models/                   # ONNX (también empaquetados en el EXE)
└── README.txt
    "1. Instala tu licencia: copia .gutoflow-license a %USERPROFILE%\.gutoflow\license.key
     2. Ejecuta GutoFlow.exe
     3. Acepta los términos de telemetría en el primer arranque"
```

### 3.5 Notas Importantes

- **NO uses `--onefile`** para todo. Desempaqueta en cada arranque y es lento con ONNX + modelos. Usa `--standalone`.
- **NO embebas la clave privada** en el binario. Solo la pública.
- **Los modelos ONNX** pueden ir empaquetados dentro del binario o como archivos adjuntos cifrados. Para la beta, Nuitka standalone + ofuscación básica es suficiente.

---

## 4. Telemetría Automática (SQLite → Telegram)

### 4.1 Esquema de Eventos Completo

| Evento | Descripción | Payload Clave |
|--------|-------------|---------------|
| `session_start` | Inicio de sesión | OS, CPU, RAM, GPU, versión |
| `session_end` | Fin de sesión | duración, fotos, clusters, overrides |
| `ingestion_batch` | Batch de 200 fotos | tiempo, raw/jpg, errores |
| `photo_analyzed` | Foto individual | hash anónimo, escena, caras, nitidez |
| `clustering_complete` | Clustering final | clusters, tamaños, tiempo |
| `culling_decision` | Decisión de IA | cluster, mantenidas, rechazadas, scores |
| `user_override` | **ORO:** Usuario corrige IA | falso positivo/negativo, features |
| `duel_resolved` | Duelo A/B | ganador, perdedor, tiempo de decisión |
| `style_applied` | Pre-edición | preset, ajustes, face-aware |
| `export_complete` | Exportación | formato, cantidad, tiempo |
| `performance_snapshot` | Rendimiento | fase, RAM, CPU, GPU VRAM |
| `error_caught` | Error recuperado | fase, tipo, mensaje |

### 4.2 Modelos de Datos (`backend/core/telemetry_models.py`)

```python
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
import hashlib
import json

@dataclass
class TelemetryEvent:
    event_type: str
    payload: dict
    session_id: str
    install_id: str
    version: str = "1.0.0-beta"
    timestamp: str = None
    event_id: str = None

    def __post_init__(self):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "version": self.version,
            "install_id": self.install_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)

def hash_photo_path(path: str) -> str:
    """Anonimiza una ruta de foto. Nunca enviamos la ruta real."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]
```

### 4.3 Almacenamiento Local (`backend/core/telemetry_store.py`)

```python
import sqlite3
import json
import gzip
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import threading

class TelemetryStore:
    """Cola local de eventos. Funciona 100% offline."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path.home() / ".gutoflow" / "telemetry"
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.base_dir / "telemetry.db"
        self.pending_dir = self.base_dir / "pending"
        self.pending_dir.mkdir(exist_ok=True)

        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                version TEXT,
                install_id TEXT,
                payload_json TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_synced ON events(synced)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON events(session_id)")
        conn.commit()

    def log(self, event: 'TelemetryEvent'):
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO events 
               (event_id, session_id, timestamp, event_type, version, install_id, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.session_id,
                event.timestamp,
                event.event_type,
                event.version,
                event.install_id,
                json.dumps(event.payload, default=str, ensure_ascii=False)
            )
        )
        conn.commit()

        if self.count_unsynced() >= 50:
            self.export_batch()

    def count_unsynced(self) -> int:
        conn = self._get_conn()
        cur = conn.execute("SELECT COUNT(*) FROM events WHERE synced = 0")
        return cur.fetchone()[0]

    def get_unsynced(self, limit: int = 500) -> List[dict]:
        conn = self._get_conn()
        cur = conn.execute(
            """SELECT event_id, session_id, timestamp, event_type, version, install_id, payload_json
               FROM events WHERE synced = 0 ORDER BY id LIMIT ?""",
            (limit,)
        )
        rows = []
        for row in cur.fetchall():
            rows.append({
                "event_id": row[0], "session_id": row[1], "timestamp": row[2],
                "event_type": row[3], "version": row[4], "install_id": row[5],
                "payload": json.loads(row[6]),
            })
        return rows

    def export_batch(self, limit: int = 500) -> Optional[Path]:
        events = self.get_unsynced(limit)
        if not events:
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sid = events[0]["session_id"][:8]
        filename = f"gutoflow_telemetry_{sid}_{ts}_{len(events)}ev.json.gz"
        filepath = self.pending_dir / filename

        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            json.dump(events, f, default=str, ensure_ascii=False)

        conn = self._get_conn()
        event_ids = [e["event_id"] for e in events]
        placeholders = ",".join("?" * len(event_ids))
        conn.execute(f"UPDATE events SET synced = 2 WHERE event_id IN ({placeholders})", event_ids)
        conn.commit()
        return filepath

    def confirm_synced(self, filepath: Path):
        try:
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                events = json.load(f)
            event_ids = [e["event_id"] for e in events]
            if event_ids:
                conn = self._get_conn()
                placeholders = ",".join("?" * len(event_ids))
                conn.execute(f"DELETE FROM events WHERE event_id IN ({placeholders})", event_ids)
                conn.commit()
            filepath.unlink(missing_ok=True)
        except Exception:
            filepath.unlink(missing_ok=True)

    def get_pending_files(self) -> List[Path]:
        return sorted(self.pending_dir.glob("*.json.gz"))

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
```

### 4.4 Envío a Telegram (`backend/core/telemetry_sender.py`)

```python
import requests
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class TelegramTelemetryBridge:
    """Envía archivos .json.gz como documentos a Telegram. Gratis, sin servidor."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._session = requests.Session()

    def send_file(self, filepath: Path, caption: str = "") -> bool:
        try:
            url = f"{self.base_url}/sendDocument"
            with open(filepath, "rb") as f:
                files = {"document": (filepath.name, f, "application/gzip")}
                data = {"chat_id": self.chat_id, "caption": caption[:1024], "parse_mode": "HTML"}
                response = self._session.post(url, files=files, data=data, timeout=30)

            if response.status_code == 200 and response.json().get("ok"):
                logger.info(f"Telemetría enviada: {filepath.name}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Error enviando telemetría: {e}")
            return False

    def send_summary(self, session_id: str, stats: dict) -> bool:
        try:
            text = (
                f"📊 <b>Guto Flow Session</b>\n"
                f"ID: <code>{session_id[:8]}</code>\n"
                f"Fotos: {stats.get('photos', 0)}\n"
                f"Clusters: {stats.get('clusters', 0)}\n"
                f"Duración: {stats.get('duration_min', 0)}min\n"
                f"Overrides: {stats.get('overrides', 0)}\n"
                f"Errores: {stats.get('errors', 0)}"
            )
            url = f"{self.base_url}/sendMessage"
            response = self._session.post(
                url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
            return response.status_code == 200 and response.json().get("ok")
        except Exception:
            return False

class TelemetryAutoSender:
    """Orquesta envío automático cada N segundos, sin bloquear la UI."""

    def __init__(self, store: 'TelemetryStore', bridge: TelegramTelemetryBridge):
        self.store = store
        self.bridge = bridge
        self.running = False
        self._thread = None

    def start(self, interval_sec: int = 300):
        import threading
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(interval_sec,), daemon=True)
        self._thread.start()

    def _loop(self, interval_sec: int):
        while self.running:
            try:
                self.flush()
            except Exception as e:
                logger.warning(f"Error en flush: {e}")
            time.sleep(interval_sec)

    def flush(self):
        while self.store.count_unsynced() >= 10:
            self.store.export_batch()

        for filepath in self.store.get_pending_files():
            success = self.bridge.send_file(filepath, caption=f"📡 Guto Flow — {filepath.name}")
            if success:
                self.store.confirm_synced(filepath)
            else:
                break

    def force_flush(self):
        while True:
            path = self.store.export_batch(limit=1000)
            if path is None:
                break
        self.flush()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
```

### 4.5 API de Alto Nivel (`backend/core/telemetry.py`)

```python
from .telemetry_models import TelemetryEvent, hash_photo_path
from .telemetry_store import TelemetryStore
from .telemetry_sender import TelegramTelemetryBridge, TelemetryAutoSender
from pathlib import Path
import platform
import psutil
import os

class GutoTelemetry:
    """API única para todo el backend. Inicializar una vez en startup."""

    def __init__(self, install_id: str, session_id: str, version: str = "1.0.0-beta"):
        self.install_id = install_id
        self.session_id = session_id
        self.version = version
        self.store = TelemetryStore()

        bot_token = os.getenv("GUTO_TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("GUTO_TELEGRAM_CHAT_ID", "")

        if bot_token and chat_id:
            bridge = TelegramTelemetryBridge(bot_token, chat_id)
            self.sender = TelemetryAutoSender(self.store, bridge)
            self.sender.start(interval_sec=300)
        else:
            self.sender = None
            print("⚠️ Telemetría local solamente (sin bot configurado)")

    def track(self, event_type: str, payload: dict):
        """Registra un evento. Nunca bloquea."""
        try:
            event = TelemetryEvent(
                event_type=event_type, payload=payload,
                session_id=self.session_id, install_id=self.install_id, version=self.version
            )
            self.store.log(event)
        except Exception:
            pass

    def flush(self):
        if self.sender:
            self.sender.force_flush()

    def close(self):
        self.flush()
        self.store.close()
        if self.sender:
            self.sender.stop()

    # ====== HELPERS ESPECÍFICOS ======

    def track_session_start(self, license_info: dict):
        self.track("session_start", {
            "os": f"{platform.system()} {platform.release()}",
            "cpu": platform.processor() or "unknown",
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "gpu": self._detect_gpu(),
            "backend_version": self.version,
            "license_tier": license_info.get("tier", "beta"),
            "license_days_remaining": license_info.get("days_remaining", 0),
        })

    def track_ingestion_batch(self, batch_size: int, duration_sec: float,
                              raw_count: int, jpg_count: int, errors: int):
        self.track("ingestion_batch", {
            "batch_size": batch_size, "duration_sec": round(duration_sec, 2),
            "raw_count": raw_count, "jpg_count": jpg_count, "errors": errors,
            "avg_time_per_photo_sec": round(duration_sec / max(batch_size, 1), 3),
        })

    def track_photo_analyzed(self, path: str, is_raw: bool, width: int, height: int,
                             scene_type: str, face_count: int, eyes_open_ratio: float,
                             blur: float, exposure: float, iso: int = 0):
        self.track("photo_analyzed", {
            "photo_hash": hash_photo_path(path), "is_raw": is_raw,
            "width": width, "height": height, "iso": iso,
            "scene_type": scene_type, "face_count": face_count,
            "eyes_open_ratio": round(eyes_open_ratio, 2),
            "blur_score": round(blur, 3), "exposure_score": round(exposure, 3),
        })

    def track_clustering(self, total_photos: int, clusters: list, duration_sec: float):
        sizes = [len(c.image_indices) for c in clusters]
        self.track("clustering_complete", {
            "total_photos": total_photos, "clusters_found": len(clusters),
            "singleton_clusters": sum(1 for s in sizes if s == 1),
            "portrait_clusters": sum(1 for c in clusters if c.scene_type == "portrait"),
            "detail_clusters": sum(1 for c in clusters if c.scene_type == "detail"),
            "avg_cluster_size": round(sum(sizes) / max(len(sizes), 1), 1),
            "max_cluster_size": max(sizes) if sizes else 0,
            "duration_sec": round(duration_sec, 2),
        })

    def track_culling_decision(self, cluster_id: str, cluster_size: int,
                               kept_indices: list, rejected_indices: list,
                               scene_type: str, scores: list, duration_sec: float):
        self.track("culling_decision", {
            "cluster_id": cluster_id, "cluster_size": cluster_size,
            "scene_type": scene_type, "kept_indices": kept_indices,
            "rejected_indices": rejected_indices,
            "kept_scores": [round(s, 3) for s in scores],
            "duration_sec": round(duration_sec, 2),
        })

    def track_user_override(self, cluster_id: str, photo_path: str,
                            ai_decision: str, user_decision: str,
                            ai_score: float, features: dict):
        self.track("user_override", {
            "cluster_id": cluster_id, "photo_hash": hash_photo_path(photo_path),
            "ai_decision": ai_decision, "user_decision": user_decision,
            "override_type": "false_negative" if ai_decision == "reject" else "false_positive",
            "ai_score": round(ai_score, 3),
            "features_at_moment": {k: round(v, 3) if isinstance(v, float) else v for k, v in features.items()},
        })

    def track_duel(self, cluster_id: str, path_a: str, path_b: str,
                   winner: str, score_a: float, score_b: float, user_time_ms: int):
        self.track("duel_resolved", {
            "cluster_id": cluster_id,
            "photo_a_hash": hash_photo_path(path_a),
            "photo_b_hash": hash_photo_path(path_b),
            "winner": winner,
            "winner_score": round(max(score_a, score_b), 3),
            "loser_score": round(min(score_a, score_b), 3),
            "user_time_ms": user_time_ms,
        })

    def track_style_applied(self, preset: str, adjustments: dict, face_aware: bool):
        self.track("style_applied", {
            "preset": preset,
            "adjustments": {k: round(v, 3) for k, v in adjustments.items()},
            "face_aware": face_aware,
        })

    def track_export(self, format_type: str, count: int, duration_sec: float):
        self.track("export_complete", {
            "format": format_type, "photos_exported": count,
            "duration_sec": round(duration_sec, 2),
        })

    def track_performance(self, phase: str, duration_sec: float):
        process = psutil.Process()
        self.track("performance_snapshot", {
            "phase": phase, "duration_sec": round(duration_sec, 3),
            "ram_mb": round(process.memory_info().rss / (1024**2), 1),
            "cpu_percent": round(process.cpu_percent(), 1),
        })

    def track_error(self, phase: str, error: Exception, recoverable: bool = True):
        self.track("error_caught", {
            "phase": phase, "error_type": type(error).__name__,
            "message": str(error)[:500], "recoverable": recoverable,
        })

    def _detect_gpu(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_name(0)
        except Exception:
            pass
        try:
            import onnxruntime as ort
            return f"ONNX: {', '.join(ort.get_available_providers())}"
        except Exception:
            pass
        return "CPU only"
```

---

## 5. Sentry para Errores

### 5.1 Instalación

```bash
pip install sentry-sdk
```

### 5.2 Configuración (`backend/core/sentry_config.py`)

```python
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
import os

def init_sentry():
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        print("⚠️ Sentry no configurado (sin SENTRY_DSN)")
        return

    sentry_logging = LoggingIntegration(
        level=logging.INFO,
        event_level=logging.ERROR
    )

    sentry_sdk.init(
        dsn=dsn,
        environment="beta",
        release="gutoflow@1.0.0-beta",
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        before_send=filter_sensitive,
        integrations=[sentry_logging],
    )

def filter_sensitive(event, hint):
    # Eliminar rutas absolutas de stack traces
    if event.get("exception"):
        for val in event["exception"].get("values", []):
            if "stacktrace" in val and "frames" in val["stacktrace"]:
                for frame in val["stacktrace"]["frames"]:
                    if "abs_path" in frame:
                        frame["abs_path"] = "[REDACTED]"
                    if "vars" in frame:
                        frame["vars"] = {k: "[REDACTED]" for k in frame["vars"]}

    event.setdefault("tags", {}).update({
        "product": "gutoflow",
        "tier": "beta",
    })
    return event
```

### 5.3 Uso en `main.py`

```python
from core.sentry_config import init_sentry

init_sentry()
```

**Gratis hasta 5,000 eventos/mes.** Para 20 testers es más que suficiente.

---

## 6. Learning Events (Oro para el Modelo)

### 6.1 Qué es Learning Data

No es solo cuántas veces usó un botón. Es:

| Señal | Valor para entrenar |
|-------|---------------------|
| **Falso Negativo** | IA rechazó, usuario recuperó → La foto tenía valor que la IA no detectó |
| **Falso Positivo** | IA mantuvo, usuario descartó → La IA sobrevaloró algo |
| **Duelo A>B** | Preferencia relativa del fotógrafo entre dos fotos similares |
| **Tiempo de decisión** | Si tardó 3s vs 300ms en decidir, la diferencia era sutil |
| **Preset de estilo** | Qué ajustes prefiere el fotógrafo (datos para taste model) |

### 6.2 Ejemplo de Sesión de Aprendizaje

```json
{
  "session_id": "gf_8a72",
  "tester_id": "anon_9f3d",
  "photos": 2847,
  "clusters": 438,
  "kept": 612,
  "learning_signals": {
    "false_negatives": 35,
    "false_positives": 12,
    "duels": 89,
    "style_applications": 612,
    "manual_stars_5": 45,
    "manual_stars_1": 23
  },
  "hardware": "RTX 3060, 32GB RAM, Ryzen 9",
  "duration_min": 31,
  "model_version": "cull-v3"
}
```

---

## 7. UI React: Consentimiento + Banner Trial

### 7.1 ConsentDialog.tsx

```tsx
// frontend/src/components/ConsentDialog.tsx
import { useState } from 'react';

interface ConsentDialogProps {
  onAccept: () => void;
  onDecline: () => void;
}

export default function ConsentDialog({ onAccept, onDecline }: ConsentDialogProps) {
  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-6">
      <div className="bg-zinc-900 max-w-xl rounded-xl p-8 text-zinc-200 shadow-2xl border border-zinc-700">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-3xl">🔒</span>
          <h2 className="text-2xl font-bold">Beta Privada — Telemetría y Aprendizaje</h2>
        </div>

        <p className="mb-4 text-sm leading-relaxed text-zinc-300">
          Bienvenido a <strong>Guto Flow Beta</strong>. Para mejorar el producto durante esta fase de prueba,
          recopilamos automáticamente datos anónimos de uso y aprendizaje.
        </p>

        <div className="bg-zinc-800/50 rounded-lg p-4 mb-6 space-y-3">
          <h3 className="font-semibold text-emerald-400 text-sm">✅ Qué recopilamos:</h3>
          <ul className="text-sm space-y-2 list-disc pl-5 text-zinc-300">
            <li><strong>Estadísticas de uso:</strong> cuántas fotos procesas, tiempos por fase, funciones utilizadas.</li>
            <li><strong>Decisiones de culling:</strong> cuando la IA sugiere descartar y tú recuperas (o viceversa).</li>
            <li><strong>Duelos A/B:</strong> qué foto eliges en comparaciones directas.</li>
            <li><strong>Estilos aplicados:</strong> qué presets de pre-edición usas más.</li>
            <li><strong>Errores técnicos:</strong> crashes y problemas de rendimiento.</li>
            <li><strong>Hardware:</strong> CPU, GPU, RAM (para optimizar rendimiento).</li>
          </ul>

          <h3 className="font-semibold text-red-400 text-sm mt-4">❌ Qué NUNCA recopilamos:</h3>
          <ul className="text-sm space-y-1 list-disc pl-5 text-zinc-400">
            <li>Tus fotografías (imagen, contenido visual, píxeles).</li>
            <li>Rutas de archivos completas o nombres de carpetas/clientes.</li>
            <li>Metadatos GPS o información de ubicación.</li>
            <li>Datos personales identificables.</li>
          </ul>
        </div>

        <p className="text-xs text-zinc-500 mb-6">
          Todo se anonimiza con hashes irreversibles. Los datos se envían automáticamente como archivos comprimidos
          cuando hay conexión a internet. Si no hay conexión, se acumulan localmente y se envían luego.
        </p>

        <div className="flex gap-3">
          <button
            onClick={onAccept}
            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-lg transition-colors"
          >
            Aceptar y comenzar
          </button>
          <button
            onClick={onDecline}
            className="flex-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 font-semibold py-3 rounded-lg transition-colors"
          >
            Usar sin telemetría
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 7.2 TrialBanner.tsx

```tsx
// frontend/src/components/TrialBanner.tsx
import { useEffect, useState } from 'react';

export default function TrialBanner() {
  const [days, setDays] = useState<number | null>(null);
  const [tier, setTier] = useState("beta");

  useEffect(() => {
    fetch('/api/license/status')
      .then(r => r.json())
      .then(data => {
        setDays(data.days_remaining);
        setTier(data.tier);
      })
      .catch(() => setDays(0));
  }, []);

  if (days === null) return null;

  const getColor = () => {
    if (days <= 7) return 'bg-red-600';
    if (days <= 30) return 'bg-amber-500';
    return 'bg-emerald-600';
  };

  const getMessage = () => {
    if (days <= 0) return '⛔ Licencia expirada. Contacta a Guto.';
    if (days <= 7) return `🔴 Trial: ${days} días restantes. ¡Renueva ahora!`;
    if (days <= 30) return `🟡 Trial: ${days} días restantes`;
    return `🟢 Guto Flow ${tier.toUpperCase()} — ${days} días restantes`;
  };

  return (
    <div className={`${getColor()} text-white text-xs font-bold px-4 py-1.5 text-center tracking-wide`}>
      {getMessage()}
    </div>
  );
}
```

### 7.3 Integración en App.tsx

```tsx
// frontend/src/App.tsx
import { useState, useEffect } from 'react';
import ConsentDialog from './components/ConsentDialog';
import TrialBanner from './components/TrialBanner';

function App() {
  const [showConsent, setShowConsent] = useState(false);
  const [telemetryEnabled, setTelemetryEnabled] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem('gutoflow_consent_v1');
    if (!consent) {
      setShowConsent(true);
    } else {
      setTelemetryEnabled(consent === 'accepted');
    }
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TrialBanner />

      {showConsent && (
        <ConsentDialog
          onAccept={() => {
            setTelemetryEnabled(true);
            setShowConsent(false);
          }}
          onDecline={() => {
            setTelemetryEnabled(false);
            setShowConsent(false);
          }}
        />
      )}

      {/* Resto de tu app */}
    </div>
  );
}

export default App;
```

---

## 8. Integración en el Pipeline

### 8.1 Startup (`backend/main.py`)

```python
import uuid
import atexit
from pathlib import Path
from core.license_manager import LicenseManager
from core.telemetry import GutoTelemetry
from core.sentry_config import init_sentry

# 1. Sentry (errores)
init_sentry()

# 2. Install ID (persistente por máquina)
INSTALL_ID_FILE = Path.home() / ".gutoflow" / "install.id"
if INSTALL_ID_FILE.exists():
    install_id = INSTALL_ID_FILE.read_text().strip()
else:
    install_id = str(uuid.uuid4())[:16]
    INSTALL_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTALL_ID_FILE.write_text(install_id)

# 3. Sesión nueva cada vez que abre la app
session_id = f"sess_{uuid.uuid4().hex[:12]}"

# 4. Inicializar telemetría
telemetry = GutoTelemetry(
    install_id=install_id,
    session_id=session_id,
    version="1.0.0-beta"
)

# 5. Verificar licencia
license_mgr = LicenseManager()
license = license_mgr.verify()
telemetry.track_session_start({
    "tier": license.tier,
    "days_remaining": license.days_remaining
})

# 6. Shutdown graceful
def on_shutdown():
    telemetry.track("session_end", {
        "duration_seconds": elapsed,  # calcular desde startup
        "photos_processed": len(all_records),
        "photos_kept": len([r for r in all_records if r.kept]),
        "clusters_found": len(clusters),
        "manual_reviews": manual_review_count,
    })
    telemetry.close()

atexit.register(on_shutdown)
```

### 8.2 En Ingesta (`backend/services/ingester.py`)

```python
# Dentro de ingest_directory o process_batch
start = time.perf_counter()
# ... procesar batch ...
elapsed = time.perf_counter() - start

telemetry.track_ingestion_batch(
    batch_size=len(batch),
    duration_sec=elapsed,
    raw_count=sum(1 for r in batch if r.is_raw),
    jpg_count=sum(1 for r in batch if not r.is_raw),
    errors=sum(1 for r in batch if r.error)
)
```

### 8.3 En Culling (¡El más importante!)

```python
# Cuando la IA decide
telemetry.track_culling_decision(
    cluster_id=f"c_{cluster_id}",
    cluster_size=len(cluster.image_indices),
    kept_indices=[0, 3],
    rejected_indices=[1, 2, 4],
    scene_type=cluster.scene_type,
    scores=[0.91, 0.88, 0.45, 0.92, 0.33],
    duration_sec=0.8
)

# Cuando el usuario corrige (ORO PURO)
telemetry.track_user_override(
    cluster_id=f"c_{cluster_id}",
    photo_path=photo.path,
    ai_decision="reject",
    user_decision="keep",
    ai_score=0.45,
    features={"blur": 0.45, "face_count": 1, "eyes_open": True}
)
```

---

## 9. Configuración del Bot de Telegram

### Paso 1: Crear el Bot

1. Abre Telegram, busca `@BotFather`
2. Envía `/newbot`
3. Nombre: `GutoFlow Telemetry`
4. Username: `gutoflow_telemetry_bot`
5. Te da un token: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`

### Paso 2: Obtener tu Chat ID

1. Abre tu bot, envía `/start`
2. Visita: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Busca: `"chat":{"id":123456789`
4. Ese número es tu `CHAT_ID`

### Paso 3: Configurar en el Build

**NO hardcodees el token en el código fuente.** Úsalo como variable de entorno al compilar:

```bash
# Windows (batch de compilación)
set GUTO_TELEGRAM_BOT_TOKEN=123456789:ABC...
set GUTO_TELEGRAM_CHAT_ID=123456789
set SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz

# macOS/Linux
export GUTO_TELEGRAM_BOT_TOKEN=123456789:ABC...
export GUTO_TELEGRAM_CHAT_ID=123456789
export SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz
```

**O mejor:** Crea un archivo `config.json` que se lee al arranque (pero no va al repo):

```json
{
  "telegram_bot_token": "123456789:ABC...",
  "telegram_chat_id": "123456789",
  "sentry_dsn": "https://xxx@yyy.ingest.sentry.io/zzz"
}
```

---

## 10. Script de Análisis de Datos

### 10.1 Procesar archivos que te llegan a Telegram

Guarda los archivos `.json.gz` en una carpeta y corre:

```python
#!/usr/bin/env python3
"""Analizador de telemetría Guto Flow. Corre en TU máquina."""
import json
import gzip
import pandas as pd
import glob
from pathlib import Path

def load_all_events(data_dir: str = "./telemetry_downloads"):
    all_events = []
    for filepath in Path(data_dir).glob("*.json.gz"):
        with gzip.open(filepath, "rt", encoding="utf-8") as f:
            all_events.extend(json.load(f))
    return pd.DataFrame(all_events)

def analyze_sessions(df: pd.DataFrame):
    starts = df[df["event_type"] == "session_start"]
    ends = df[df["event_type"] == "session_end"]

    print(f"\n📊 SESIONES: {len(starts)}")
    print(f"   Usuarios únicos: {starts['install_id'].nunique()}")
    print(f"   OS más común: {starts['payload'].apply(lambda x: x.get('os', 'unknown')).mode()[0]}")

    # Hardware
    gpus = starts['payload'].apply(lambda x: x.get('gpu', 'unknown'))
    print(f"\n🖥️  GPUs detectadas:")
    for gpu, count in gpus.value_counts().head(5).items():
        print(f"   {count}x {gpu}")

def analyze_learning(df: pd.DataFrame):
    overrides = df[df["event_type"] == "user_override"]
    duels = df[df["event_type"] == "duel_resolved"]

    print(f"\n🧠 APRENDIZAJE:")
    print(f"   Overrides totales: {len(overrides)}")

    fn = overrides[overrides["payload"].apply(lambda x: x.get("override_type") == "false_negative")]
    fp = overrides[overrides["payload"].apply(lambda x: x.get("override_type") == "false_positive")]

    print(f"   Falsos Negativos (IA rechazó, user recuperó): {len(fn)}")
    print(f"   Falsos Positivos (IA mantuvo, user descartó): {len(fp)}")

    if len(fn) > 0:
        print(f"\n   ⚠️  Fotos que la IA está perdiendo:")
        print(f"      Blur promedio: {fn['payload'].apply(lambda x: x['features_at_moment'].get('blur', 0)).mean():.3f}")
        print(f"      Face count promedio: {fn['payload'].apply(lambda x: x['features_at_moment'].get('face_count', 0)).mean():.1f}")

    print(f"\n   🤺 Duelos resueltos: {len(duels)}")
    if len(duels) > 0:
        avg_time = duels['payload'].apply(lambda x: x.get('user_time_ms', 0)).mean()
        print(f"      Tiempo promedio de decisión: {avg_time:.0f}ms")

def analyze_performance(df: pd.DataFrame):
    ingest = df[df["event_type"] == "ingestion_batch"]
    clustering = df[df["event_type"] == "clustering_complete"]
    perf = df[df["event_type"] == "performance_snapshot"]

    print(f"\n⚡ RENDIMIENTO:")
    if len(ingest) > 0:
        avg_per_photo = ingest['payload'].apply(lambda x: x.get('avg_time_per_photo_sec', 0)).mean()
        print(f"   Ingesta: {avg_per_photo:.3f}s por foto")

    if len(clustering) > 0:
        avg_cluster_time = clustering['payload'].apply(lambda x: x.get('duration_sec', 0)).mean()
        print(f"   Clustering: {avg_cluster_time:.2f}s promedio")

    if len(perf) > 0:
        ram = perf['payload'].apply(lambda x: x.get('ram_mb', 0)).max()
        print(f"   RAM pico: {ram:.0f}MB")

def analyze_styles(df: pd.DataFrame):
    styles = df[df["event_type"] == "style_applied"]
    if len(styles) == 0:
        return

    print(f"\n🎨 ESTILOS:")
    presets = styles['payload'].apply(lambda x: x.get('preset', 'unknown'))
    for preset, count in presets.value_counts().head(5).items():
        print(f"   {count}x {preset}")

if __name__ == "__main__":
    df = load_all_events()
    print(f"📦 Total de eventos cargados: {len(df)}")

    analyze_sessions(df)
    analyze_learning(df)
    analyze_performance(df)
    analyze_styles(df)

    # Exportar a CSV para análisis en Excel/Sheets
    df.to_csv("telemetry_analysis.csv", index=False)
    print(f"\n✅ Exportado a telemetry_analysis.csv")
```

### 10.2 Ejemplo de Salida

```
📦 Total de eventos cargados: 15,420

📊 SESIONES: 23
   Usuarios únicos: 8
   OS más común: Windows 11

🖥️  GPUs detectadas:
   12x NVIDIA RTX 3060
   6x NVIDIA RTX 4090
   3x CPU only
   2x NVIDIA RTX 3080

🧠 APRENDIZAJE:
   Overrides totales: 347
   Falsos Negativos (IA rechazó, user recuperó): 198
   Falsos Positivos (IA mantuvo, user descartó): 149

   ⚠️  Fotos que la IA está perdiendo:
      Blur promedio: 0.423
      Face count promedio: 1.2

   🤺 Duelos resueltos: 892
      Tiempo promedio de decisión: 1240ms

⚡ RENDIMIENTO:
   Ingesta: 0.234s por foto
   Clustering: 8.4s promedio
   RAM pico: 4200MB

🎨 ESTILOS:
   312x wedding_bright
   198x portrait_soft
   87x documentary_neutral
```

---

## 11. Flujo de Distribución

### Para cada colega tester:

```bash
# 1. Tú generas la licencia (en tu máquina)
python tools/generate_license.py colega@email.com 90 50000 beta
# → colega_at_email_com.gutoflow-license

# 2. Compilas con Nuitka (con variables de entorno del bot)
set GUTO_TELEGRAM_BOT_TOKEN=123456:ABC...
set GUTO_TELEGRAM_CHAT_ID=123456789
set SENTRY_DSN=https://...
python -m nuitka --standalone ... backend/main.py

# 3. Empaquetas
mkdir dist/GutoFlow-Beta-v1.0.0
cp build/GutoFlow.exe dist/GutoFlow-Beta-v1.0.0/
cp README-Beta.txt dist/GutoFlow-Beta-v1.0.0/
# NO incluyas la licencia en el ZIP general

# 4. Envías por email/WeTransfer:
#    - GutoFlow-Beta-v1.0.0.zip
#    - colega_at_email_com.gutoflow-license (archivo aparte)
```

### README para el Tester

```text
GUTO FLOW BETA v1.0.0
=====================

1. INSTALACIÓN
   - Descomprime GutoFlow-Beta-v1.0.0.zip en cualquier carpeta.
   - Crea la carpeta: %USERPROFILE%\.gutoflow (o ~/.gutoflow en Mac)
   - Copia tu archivo .gutoflow-license a:
     %USERPROFILE%\.gutoflow\license.key

2. PRIMER ARRANQUE
   - Ejecuta GutoFlow.exe
   - Acepta los términos de telemetría (puedes usar sin telemetría, pero ayuda mucho)
   - Verás un banner verde con los días restantes de tu trial

3. USO
   - Importa una carpeta de fotos (JPG o RAW)
   - Revisa los clusters y decisiones de la IA
   - Corrige cuando la IA se equivoque (¡eso nos ayuda a aprender!)
   - Exporta a Lightroom/XMP

4. SOPORTE
   - WhatsApp: [tu número]
   - Email: [tu email]
   - Si la app crashea, los errores llegan automáticamente al equipo.

5. EXPIRACIÓN
   - Tu trial expira en 90 días.
   - Contacta a Guto para extender o adquirir licencia completa.
```

---

## 12. Checklist de Implementación

| # | Tarea | Tiempo | Prioridad |
|---|-------|--------|-----------|
| 1 | Generar claves RSA (`private_key.pem`, `public_key.pem`) | 2 min | 🔴 Crítica |
| 2 | Copiar `license_manager.py` al proyecto | 5 min | 🔴 Crítica |
| 3 | Copiar `generate_license.py` a `tools/` (solo local) | 2 min | 🔴 Crítica |
| 4 | Copiar `telemetry_models.py`, `telemetry_store.py`, `telemetry_sender.py`, `telemetry.py` | 10 min | 🔴 Crítica |
| 5 | Copiar `sentry_config.py` e instalar `sentry-sdk` | 5 min | 🟠 Alta |
| 6 | Crear bot de Telegram y obtener token + chat_id | 5 min | 🔴 Crítica |
| 7 | Añadir `GutoTelemetry` al startup de `main.py` | 10 min | 🔴 Crítica |
| 8 | Integrar `track_*` en ingesta, culling, duelos, export | 30 min | 🔴 Crítica |
| 9 | Copiar `ConsentDialog.tsx` y `TrialBanner.tsx` al frontend | 15 min | 🟠 Alta |
| 10 | Integrar consentimiento y banner en `App.tsx` | 10 min | 🟠 Alta |
| 11 | Compilar con Nuitka standalone (probar en máquina limpia) | 1 h | 🔴 Crítica |
| 12 | Generar licencia de prueba y testear end-to-end | 30 min | 🔴 Crítica |
| 13 | Distribuir a 1 colega como prueba piloto | 15 min | 🟡 Media |
| 14 | Revisar datos que llegan a Telegram y Sentry | 20 min | 🟡 Media |
| 15 | Usar script `analyze_telemetry.py` con datos reales | 10 min | 🟢 Baja |

**Tiempo total estimado: 4–5 horas de trabajo + 1 hora de compilación/test.**

---

## 🎯 Resumen de Seguridad y Privacidad

| Amenaza | Mitigación |
|---------|-----------|
| **Leer mi código Python** | Nuitka compila a binario nativo |
| **Generar licencias falsas** | JWT RS256: ellos solo tienen clave pública |
| **Extender trial editando fecha** | Firma criptográfica se invalida |
| **Ver modelos ONNX** | Empaquetados dentro del binario Nuitka |
| **Robar fotos del usuario** | **Nunca se envían**. Solo hashes y estadísticas. |
| **Identificar rutas de archivos** | Hashes SHA256 truncados, nunca rutas reales |
| **Bloquear telemetría** | Funciona offline; si falla envío, sigue operando |
| **Privacidad de fotos** | Consentimiento explícito; todo anónimo |

---

**Documento generado para Guto Flow Beta v1.0.0 — Uso interno únicamente.**
