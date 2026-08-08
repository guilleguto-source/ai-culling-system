# build.ps1 — Pipeline de build completo para Guto Flow (Windows)
# ============================================================
# Uso:
#   .\scripts\build.ps1              # build normal
#   .\scripts\build.ps1 -SkipTests  # saltar pytest
#   .\scripts\build.ps1 -SkipBackend  # solo frontend + empaquetado
#
param(
    [switch]$SkipTests = $false,
    [switch]$SkipBackend = $false,
    [switch]$SkipVerify = $false
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$BackendVenv = Join-Path $Root "backend\.venv\Scripts\python.exe"
$PythonCmd = if (Test-Path $BackendVenv) { $BackendVenv } else { "python" }

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Guto Flow — Build Pipeline" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 0. Verificar dependencias ────────────────────────────────────────────────
Write-Host "[0/6] Verificando dependencias..." -ForegroundColor Yellow
$nodeVersion = (node --version 2>$null)
$npmVersion  = (npm --version 2>$null)
$pyVersion   = (& $PythonCmd --version 2>$null)

if (-not $nodeVersion) { Write-Error "Node.js no encontrado. Instala Node.js 18+." }
if (-not $pyVersion)   { Write-Error "Python no encontrado en $PythonCmd" }

Write-Host "  Node: $nodeVersion | npm: $npmVersion"
Write-Host "  Python: $pyVersion"

# ── 1. Tests de backend ──────────────────────────────────────────────────────
if (-not $SkipTests) {
    Write-Host ""
    Write-Host "[1/6] Corriendo tests del backend..." -ForegroundColor Yellow
    Push-Location $Root
    & $PythonCmd -m pytest backend/tests/ -q --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests fallaron. Abortando build."
    }
    Pop-Location
    Write-Host "  ✅ Todos los tests pasaron." -ForegroundColor Green
} else {
    Write-Host "[1/6] Tests omitidos (--SkipTests)" -ForegroundColor Gray
}

# ── 2. Build del frontend (Vite) ─────────────────────────────────────────────
Write-Host ""
Write-Host "[2/6] Construyendo frontend con Vite..." -ForegroundColor Yellow
Push-Location $Root
npm run build:frontend
if ($LASTEXITCODE -ne 0) { Write-Error "Falló vite build." }
Pop-Location
Write-Host "  ✅ Frontend compilado en dist/renderer/" -ForegroundColor Green

# ── 3. Compilar Electron main process ────────────────────────────────────────
Write-Host ""
Write-Host "[3/6] Compilando Electron (TypeScript → JS)..." -ForegroundColor Yellow
Push-Location $Root
npm run build:electron
if ($LASTEXITCODE -ne 0) { Write-Error "Falló tsc para Electron." }
Pop-Location
Write-Host "  ✅ Electron main compilado en dist/main/" -ForegroundColor Green

# ── 4. Build del backend (PyInstaller) ───────────────────────────────────────
if (-not $SkipBackend) {
    Write-Host ""
    Write-Host "[4/6] Empaquetando backend con PyInstaller..." -ForegroundColor Yellow
    Push-Location $Root

    # Instalar dependencias del backend si es necesario
    & $PythonCmd -m pip install pyinstaller --quiet

    & $PythonCmd -m PyInstaller backend.spec --clean --noconfirm
    if ($LASTEXITCODE -ne 0) { Write-Error "Falló PyInstaller." }

    Pop-Location
    Write-Host "  ✅ Backend empaquetado en dist/backend/" -ForegroundColor Green
} else {
    Write-Host "[4/6] Backend omitido (--SkipBackend)" -ForegroundColor Gray
}

# ── 5. Verificar ejecutable ───────────────────────────────────────────────────
if (-not $SkipVerify -and -not $SkipBackend) {
    Write-Host ""
    Write-Host "[5/6] Verificando ejecutable del backend..." -ForegroundColor Yellow
    Push-Location $Root
    & $PythonCmd scripts/verify_build.py
    if ($LASTEXITCODE -ne 0) { Write-Error "El ejecutable del backend no respondió. Abortando." }
    Pop-Location
    Write-Host "  ✅ Backend ejecutable verificado." -ForegroundColor Green
} else {
    Write-Host "[5/6] Verificación omitida" -ForegroundColor Gray
}

# ── 6. Electron-builder → instalador NSIS ────────────────────────────────────
Write-Host ""
Write-Host "[6/6] Generando instalador con electron-builder..." -ForegroundColor Yellow
Push-Location $Root
npm exec -- electron-builder --win nsis
if ($LASTEXITCODE -ne 0) { Write-Error "Falló electron-builder." }
Pop-Location

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ BUILD COMPLETADO" -ForegroundColor Green
Write-Host "  Instalador en: release/GutoFlow-Setup-*.exe" -ForegroundColor Green
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
