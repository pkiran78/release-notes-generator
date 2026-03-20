import os

# Load from env with safe defaults
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
# OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "release-notes-llama3")

# LLM options: temperature etc. (Ollama uses 'options' not 'parameters')
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "8192"))  # context window (depends on model)

# App defaults
DEFAULT_GROUP_CONVENTIONAL = True
DEFAULT_OUTPUT_MARKDOWN = True

# LLM provider configurations
LLM_PROVIDERS = {
    "Ollama": {
        "base_url": OLLAMA_HOST.rstrip("/") + "/v1",
        "model": OLLAMA_MODEL,
        "api_key_env": "OPENAI_API_KEY",
        "api_key_default": "ollama",
    },
    "DellAI": {
        "base_url": os.getenv("DELLAI_BASE_URL", "https://aia.gateway.dell.com/genai/dev/v1/"),
        "model": os.getenv("DELLAI_MODEL", "gpt-oss-120b"),
        "api_key_env": None,  # uses aia_auth SSO token
    },
}

DEFAULT_LLM_PROVIDER = "Ollama"

# Git safety
GIT_CLONE_DEPTH = os.getenv("GIT_CLONE_DEPTH", "0")  # "0" means full history