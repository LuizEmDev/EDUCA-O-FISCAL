#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m PyInstaller --noconfirm --onefile --windowed --name MissaoFiscal main.py

echo
echo "Arquivo gerado em: dist/MissaoFiscal"
