# ================================
#  Base Image
# ================================
FROM python:3.12-slim

# Avoid Python writing .pyc files & use buffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ================================
#  System Dependencies
# ================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ================================
#  Working Directory
# ================================
WORKDIR /app

# ================================
#  Copy Code
# ================================
COPY . /app

# ================================
#  Install Python Dependencies
# ================================
# (Assuming you have requirements.txt, if not, I can generate one)
RUN git config --global http.sslverify false
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# ================================
#  Environment Variables
# ================================
# Default Ollama host for local dev.
# On macOS/Windows Docker: host.docker.internal works.
ENV OLLAMA_HOST=http://127.0.0.1:11434

# Default model from config.py (your custom MODELFILE model)
ENV OLLAMA_MODEL=release-notes-llama3

# ================================
#  Expose Gradio Port
# ================================
EXPOSE 7860

# ================================
#  Run App
# ================================
CMD ["python", "src/app.py"]