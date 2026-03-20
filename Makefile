# Makefile for AI Release Notes (Ollama)
# Usage:
#   make create       # Build the custom model from the Modelfile
#   make rebuild      # Rebuild (force) the model
#   make show         # Show model info (params baked in)
#   make test         # Quick smoke test generation
#   make list         # List local models
#   make run          # Run the Gradio app in Docker (Ollama)

MODEL_NAME := release-notes-llama3
MODELFILE  := release-notes-model.Modelfile
APP_FILE   := src/app.py

# Default Ollama host; change if you run remotely.
export OLLAMA_HOST ?= http://127.0.0.1:11434

.PHONY: create rebuild show test list run

create:
	@echo "==> Creating model $(MODEL_NAME) from $(MODELFILE)"
	ollama create $(MODEL_NAME) -f $(MODELFILE)

rebuild:
	@echo "==> Rebuilding model $(MODEL_NAME) from $(MODELFILE)"
	-ollama rm $(MODEL_NAME)
	ollama create $(MODEL_NAME) -f $(MODELFILE)

show:
	@echo "==> Showing model info for $(MODEL_NAME)"
	ollama show $(MODEL_NAME)

list:
	@echo "==> Listing local models"
	ollama list

test:
	@echo "==> Quick test: ask the model to summarize a tiny changelog"
	@printf '%s\n' \
		'{ "model": "$(MODEL_NAME)",' \
		'  "messages": [' \
		'    {"role":"system","content":"You generate release notes."},' \
		'    {"role":"user","content":"Generate concise release notes for: feat(api): add /health, fix(ci): flaky test retry, docs: README badge"}' \
		'  ],' \
		'  "stream": false }' \
	| curl -s $(OLLAMA_HOST)/api/chat -d @- \
	| jq -r '.message.content'

build:
	@echo "Building Docker image and installing dependencies"
	@docker build -t release-notes-ai .
	@echo "Docker image build completed"

run:
	@echo "Running Release notes generator app (Ollama)"
	@docker run --rm --network=host release-notes-ai

clean:
	@echo ""
	@echo "--------------------------------------------------------------------"
	@echo "Removing make directory: $(BUILD_DIR)"
	@rm -rf $(BUILD_DIR)
	@echo "Removing *.pyc *.c and __pycache__/ files"
	@find . -type f -name "*.pyc" | xargs rm -vrf
	@find . -type f -name "*.c" | xargs rm -vrf
	@find . -type f -name "*.so" | xargs rm -vrf
	@find . -type f -name "coverage.xml" | xargs rm -vrf
	@find . -type f -name "junitxml.xml" | xargs rm -vrf
	@find . -type d -name "__pycache__" | xargs rm -vrf
	@find . -type d -name "*egg-info" | xargs rm -vrf
	@echo ""
	@echo "Done."
	@echo ""