#!/usr/bin/env bash
# Instalação no macOS (Apple Silicon). Rode dentro da pasta jarvis/:  bash scripts/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

command -v brew >/dev/null || { echo "Instale o Homebrew antes: https://brew.sh"; exit 1; }
brew list python@3.11 >/dev/null 2>&1 || brew install python@3.11
brew list portaudio >/dev/null 2>&1 || brew install portaudio

python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

[ -f .env ] || cp .env.example .env
mkdir -p assets

cat <<MSG

Pronto. Falta:
  1. Editar o arquivo .env (chaves da Anthropic e do ElevenLabs, ID da voz)
  2. Colocar sua música de abertura em assets/intro.mp3
  3. Rodar:  source .venv/bin/activate && python main.py
  4. Na 1ª execução, permitir o Microfone para o Terminal quando o macOS pedir
MSG
