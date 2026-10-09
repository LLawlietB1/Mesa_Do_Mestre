# Mesa do Mestre — versão LOCAL (sem Vercel, sem Neon, sem Blob, sem custo).
# Tudo fica nesta pasta: banco de dados e imagens em local\dados\.
# Uso: dê dois cliques em iniciar.bat (ou rode este arquivo no PowerShell).
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$dados = Join-Path $PSScriptRoot "dados"
New-Item -ItemType Directory -Force $dados | Out-Null

# 1) Ambiente virtual e dependências (só na primeira vez)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual (primeira vez)..." -ForegroundColor Cyan
    python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"
$ErrorActionPreference = "Continue"
& $py -c "import flask, flask_sqlalchemy, flask_migrate, argon2, PIL, psycopg" 2>$null
$depsOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $depsOk) {
    Write-Host "Instalando dependências (primeira vez)..." -ForegroundColor Cyan
    & $py -m pip install -q -r requirements.txt
}

# 2) Configuração 100% local (sobrepõe qualquer .env: nada de nuvem)
$env:MESA_ENV = "development"
$env:DATABASE_URL = "sqlite:///" + ($dados -replace "\\", "/") + "/mesa.sqlite3"
$env:BLOB_READ_WRITE_TOKEN = ""        # imagens ficam no banco local
$env:TWILIO_ACCOUNT_SID = ""           # sem envio pago de mensagens
$env:RESEND_API_KEY = ""
$keyFile = Join-Path $dados ".secret_key"
if (-not (Test-Path $keyFile)) { & $py -c "import secrets; print(secrets.token_hex(32))" | Set-Content -NoNewline $keyFile }
$env:SECRET_KEY = (Get-Content $keyFile -Raw).Trim()
$env:HOST = "127.0.0.1"
if (-not $env:PORT) { $env:PORT = "5000" }

# 3) Cria/atualiza o banco
$env:FLASK_APP = "run.py"
# (cmd /c: o Alembic escreve avisos informativos em stderr, que o PowerShell 5.1 trataria como erro)
cmd /c ".\.venv\Scripts\flask.exe db upgrade >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Write-Host "Falha ao preparar o banco de dados." -ForegroundColor Red; exit 1 }

# 4) Abre o navegador e inicia
Write-Host ""
Write-Host "Mesa do Mestre rodando em http://127.0.0.1:$($env:PORT)" -ForegroundColor Green
Write-Host "Dados em: $dados" -ForegroundColor DarkGray
Write-Host "A primeira conta criada vira administradora. Feche esta janela para encerrar." -ForegroundColor DarkGray
if (-not $env:MESA_NO_BROWSER) { Start-Process "http://127.0.0.1:$($env:PORT)/cadastro" }
& $py run.py
