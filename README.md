# 🤖📝 AI-Powered Release Notes Generator (Gradio + Ollama)

Generate clean, structured release notes from Git commits using a local LLM via **Ollama**.
- Works with local path or remote Git URLs.
- Date range and branch/tag selection.
- AI mode (Ollama) or deterministic conventional-commit grouping as fallback.

## Prerequisites
- Ubuntu/Linux with Internet connectivity (works on WSL2)
- Python 3.9+

## Quick Start (Recommended)
Run the prerequisite script from the repo root:

```bash
chmod +x prereq.sh
./prereq.sh

# Build Docker image using: make build

# Run release notes generator: make run