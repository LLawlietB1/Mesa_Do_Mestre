# Prepara o ambiente local (venv, dependências, .env e banco) e opcionalmente inicia a aplicação.
# Uso:  .\setup.ps1          (prepara)   |   .\setup.ps1 -Run   (prepara e inicia)
param([switch]$Run)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

$env:FLASK_APP = "run.py"
& .\.venv\Scripts\flask.exe db upgrade
Write-Host "`nPronto. Inicie com:  .\.venv\Scripts\python.exe run.py   e abra http://127.0.0.1:5000 (crie sua conta em /cadastro)" -ForegroundColor Green
if ($Run) { & .\.venv\Scripts\python.exe run.py }
