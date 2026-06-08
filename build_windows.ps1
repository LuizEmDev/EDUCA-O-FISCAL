$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

if (-not (Test-Path -LiteralPath ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name MissaoFiscal main.py

Write-Host ""
Write-Host "Arquivo gerado em: dist\MissaoFiscal.exe"
