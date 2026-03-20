#!/usr/bin/env bash
set -euo pipefail

echo "==> Updating apt..."
sudo apt-get update -y

echo "==> Installing prerequisites (zstd, curl, make)..."
sudo apt-get install -y zstd curl make ca-certificates git

echo "==> Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "==> Starting Ollama server in background..."
# Start ollama in background and save logs
nohup ollama serve > ollama-serve.log 2>&1 &

sleep 2

echo "==> Checking Ollama is running..."
if ! pgrep -f "ollama serve" >/dev/null; then
  echo "ERROR: Ollama server did not start. Check ollama-serve.log"
  exit 1
fi

echo "==> Pulling model llama3:latest..."
ollama pull llama3:latest

echo "==> Creating custom model (mymodel) from Modelfile..."
if [ ! -f "release-notes-model.Modelfile" ]; then
  echo "ERROR: Modelfile not found in current directory: $(pwd)"
  echo "Run this script from your repo root (where Modelfile exists)."
  exit 1
fi

ollama create mymodel -f release-notes-model.Modelfile

echo "==> Running make build..."
make -f Makefile build

echo "==> Running make run..."
make -f Makefile run
