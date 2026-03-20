import json
import socket
from typing import Dict, List, Optional

import os
import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI

from config import OLLAMA_HOST, LLM_PROVIDERS, LLM_TEMPERATURE, LLM_NUM_CTX

def _ollama_alive(host: str) -> bool:
    try:
        # quick TCP check
        url = host.replace("http://", "").replace("https://", "")
        hostname, port = url.split(":")
        with socket.create_connection((hostname, int(port)), timeout=0.5):
            return True
    except Exception:
        return False

def _build_client(provider: str) -> tuple:
    """Return (OpenAI client, model_name) for the given provider."""
    cfg = LLM_PROVIDERS[provider]

    if provider == "DellAI":
        token = os.getenv("DELLAI_TOKEN")
        if not token:
            from aia_auth import auth
            access_token = auth.sso()
            token = access_token.token
        http_client = httpx.Client(verify=False)
        client = OpenAI(
            base_url=cfg["base_url"],
            http_client=http_client,
            api_key=token,
        )
    else:
        client = OpenAI(
            base_url=cfg["base_url"],
            api_key=os.getenv(cfg["api_key_env"], cfg.get("api_key_default", "")),
        )

    return client, cfg["model"]

def generate_release_notes_ai(
    commits: List[Dict],
    release_title: Optional[str] = None,
    audience: str = "engineering",
    style: str = "conventional",  # 'conventional' | 'changelog' | 'executive'
    extra_context: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: str = "Ollama",
) -> str:
    """
    Use the selected LLM provider to produce well-structured Markdown release notes.
    """
    if not commits:
        return "No commits found in the selected range."

    if provider == "Ollama" and not _ollama_alive(OLLAMA_HOST):
        raise RuntimeError(f"Ollama is not reachable at {OLLAMA_HOST}. Is `ollama serve` running?")

    # Detect multi-repo mode
    multi_repo = any(c.get("source_repos") for c in commits)

    # Prepare compact JSON for the model
    slim_commits = []
    for c in commits:
        entry = {
            "hash": c["hash"][:7],
            "date": c["date"],
            "author": c["author"],
            "subject": c["subject"],
            "body": c.get("body", "")[:2000],  # safety truncation
        }
        if multi_repo and c.get("source_repos"):
            entry["source_repos"] = c["source_repos"]
        slim_commits.append(entry)
    commits_json = json.dumps(slim_commits, ensure_ascii=False)

    multi_repo_instructions = """
- These commits come from MULTIPLE repositories. Each commit has a 'source_repos' field listing which repo(s) it appears in.
- If a commit appears in multiple repos (multiple entries in source_repos), treat it as a SINGLE feature/change — do NOT duplicate it.
- Where helpful, mention the affected repo(s) in parentheses after each bullet, e.g. '(repo-a, repo-b)'.
- Group by category first, not by repository.
""" if multi_repo else ""

    sys_prompt = f"""You are an expert release notes writer.
- Produce clear, accurate, non-hallucinated release notes in **Markdown**.
- Only use the information in the provided commits JSON.
- Prefer grouping by categories: Features, Fixes, Performance, Refactor, Docs, Tests, CI, Build, Breaking Changes, Others.
- Write concise, actionable bullets. Avoid duplications.
- If you infer a PR number from subject like '(#123)', you may include it verbatim, but do not guess missing data.
- Keep tone suitable for '{audience}' audience.
- Style preset: {style}.
{multi_repo_instructions}
"""

    user_prompt = f"""Generate release notes. Title: "{release_title or 'Release Notes'}".
Commits (JSON array):
{commits_json}

Instructions:
- Start with '# {release_title or "Release Notes"}'.
- Then write a one-paragraph summary.
- Then sections with '## <Category>' and bullet points.
- Under 'Breaking Changes' explicitly call out any breaking changes if evident (e.g., '!' in conventional commits).
- End with '### Contributors' listing unique authors (from commits).
{"Additional context:\n" + extra_context if extra_context else ""}"""

    client, default_model = _build_client(provider)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        resp = client.chat.completions.create(
            model=model or default_model,
            messages=messages,
            temperature=float(temperature if temperature is not None else LLM_TEMPERATURE),
            timeout=300,
        )
    except APITimeoutError:
        raise RuntimeError("Timeout: OpenAI API call took longer than 5 minutes.")
    except APIConnectionError as e:
        raise RuntimeError(f"Connection error to {provider}: {e.__cause__ or e}")

    text = (resp.choices[0].message.content or "") if resp.choices else ""
    if not text.strip():
        raise RuntimeError("LLM returned empty response.")
    return text.strip()