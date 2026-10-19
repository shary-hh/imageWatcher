<#
.SYNOPSIS
    Genera imageWatcher.exe en Windows con PyInstaller.

.DESCRIPTION
    Crea el ejecutable a partir de packaging/windows/imagewatcher.spec.
    Requiere que el Python usado tenga PyGObject (gi) y GTK3 disponibles;
    en Windows eso se consigue con MSYS2 + gvsbuild. Ver README.md.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1
#>
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $Here "..\..")
Set-Location $Root

Write-Host "==> Comprobando dependencias de Python..." -ForegroundColor Cyan
& $Python -c "import sys; print(sys.version)"

$has_gi = $true
& $Python -c "import gi" 2>$null
if ($LASTEXITCODE -ne 0) {
    $has_gi = $false
    Write-Warning "No se encontro PyGObject (gi). El .exe se generara pero no arrancara sin GTK3."
    Write-Warning "Instala PyGObject en Windows con MSYS2/gvsbuild (ver packaging\windows\README.md)."
}

Write-Host "==> Instalando/actualizando herramientas de empaquetado..." -ForegroundColor Cyan
& $Python -m pip install --upgrade pip pyinstaller pillow

Write-Host "==> Empaquetando con PyInstaller..." -ForegroundColor Cyan
& $Python -m PyInstaller --noconfirm --clean (Join-Path $Here "imagewatcher.spec")

$exe = Join-Path $Root "dist\imageWatcher.exe"
if (Test-Path $exe) {
    Write-Host "==> Listo: $exe" -ForegroundColor Green
    if (-not $has_gi) {
        Write-Warning "Recuerda: el .exe necesita GTK3 + PyGObject para ejecutarse en Windows."
    }
} else {
    Write-Error "No se genero el ejecutable."
}
