import os
from datetime import datetime
from typing import Optional, Tuple
 
import gradio as gr
 
from config import (
    DEFAULT_GROUP_CONVENTIONAL,
    DEFAULT_OUTPUT_MARKDOWN,
    GIT_CLONE_DEPTH,
    DEFAULT_LLM_PROVIDER,
)
from git_utils import clone_or_use_repo, checkout_ref, get_commits, get_commits_multi_repo, normalize_date_value
from notes_formatter import format_release_notes_plain
from ai_summarizer import generate_release_notes_ai
from publisher import publish_release_notes
 
def _parse_repo_lines(text: str, shared_token: str, shared_branch: str):
    """
    Parse multi-line repo input. Each line can be:
      - Just a URL/path
      - URL/path | branch
      - URL/path | branch | token
    Shared token/branch are used as defaults when not specified per-line.
    """
    entries = []
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        url = parts[0]
        branch = parts[1] if len(parts) > 1 and parts[1] else shared_branch
        token = parts[2] if len(parts) > 2 and parts[2] else shared_token
        entries.append({"url": url, "branch": branch, "token": token})
    return entries


def generate_handler(
        repo_url_or_path: str,
        access_token: str,
        branch_or_tag: str,
        start_date_in,
        end_date_in,
        use_ai: bool,
        audience: str,
        extra_context: str,
) -> Tuple[str, str]:
    if not repo_url_or_path or not repo_url_or_path.strip():
        return ("❌ Please provide at least one Git repository URL or local path.", "")

    # normalize_date_value already accepts str|date|None; DateTime will give str
    start_date = normalize_date_value(start_date_in)
    end_date = normalize_date_value(end_date_in)

    try:
        if start_date and end_date:
            sd = datetime.fromisoformat(start_date)
            ed = datetime.fromisoformat(end_date)
            if sd > ed:
                return ("❌ Start date must be on or before end date.", "")
    except Exception:
        return ("❌ Invalid date format. Use YYYY-MM-DD.", "")

    shared_token = (access_token or "").strip()
    shared_branch = (branch_or_tag or "").strip()
    repo_entries = _parse_repo_lines(repo_url_or_path, shared_token, shared_branch)

    if not repo_entries:
        return ("❌ No valid repository URLs found in the input.", "")

    is_multi = len(repo_entries) > 1

    # --- Single-repo path (backward compatible) ---
    if not is_multi:
        entry = repo_entries[0]
        url = entry["url"]
        if entry["token"]:
            import re
            url = re.sub(
                r'^(https?://)',
                lambda m: f"{m.group(1)}{entry['token']}@",
                url,
            )
        repo_path = None
        temp = False
        try:
            repo_path, temp = clone_or_use_repo(url, depth=GIT_CLONE_DEPTH)
            checkout_ref(repo_path, entry["branch"])
            commits = get_commits(repo_path, start_date, end_date)

            if use_ai:
                notes = generate_release_notes_ai(
                    commits=commits,
                    audience=audience or "engineering",
                    extra_context=extra_context or None,
                    provider=DEFAULT_LLM_PROVIDER,
                )
            else:
                notes = format_release_notes_plain(
                    commits,
                    group_conventional=DEFAULT_GROUP_CONVENTIONAL,
                    markdown=DEFAULT_OUTPUT_MARKDOWN,
                    include_hash=True,
                )

            branch_info = entry["branch"]
            status = (
                f"✅ Generated release notes "
                f"{f'from {start_date} ' if start_date else ''}"
                f"{f'to {end_date} ' if end_date else ''}"
                f"{f'on {branch_info} ' if branch_info else ''}"
                f"({len(commits)} commit(s))"
            ).strip()
            return (status, notes)
        except Exception as e:
            return (f"❌ Error: {e}", "")
        finally:
            if temp and repo_path and os.path.isdir(repo_path):
                import shutil
                shutil.rmtree(repo_path, ignore_errors=True)

    # --- Multi-repo path ---
    cloned_paths = []
    try:
        commits, errors, cloned_paths = get_commits_multi_repo(
            repo_entries, start_date, end_date, depth=GIT_CLONE_DEPTH,
        )

        if use_ai:
            notes = generate_release_notes_ai(
                commits=commits,
                audience=audience or "engineering",
                extra_context=extra_context or None,
                provider=DEFAULT_LLM_PROVIDER,
            )
        else:
            notes = format_release_notes_plain(
                commits,
                group_conventional=DEFAULT_GROUP_CONVENTIONAL,
                markdown=DEFAULT_OUTPUT_MARKDOWN,
                include_hash=True,
            )

        repo_names = [e['url'].rstrip('/').rsplit('/', 1)[-1].replace('.git', '') for e in repo_entries]
        error_note = f" | Errors: {'; '.join(errors)}" if errors else ""
        status = (
            f"✅ Generated release notes from {len(repo_entries)} repos "
            f"({', '.join(repo_names)}) "
            f"{f'from {start_date} ' if start_date else ''}"
            f"{f'to {end_date} ' if end_date else ''}"
            f"({len(commits)} unique commit(s)){error_note}"
        ).strip()
        return (status, notes)
    except Exception as e:
        return (f"❌ Error: {e}", "")
    finally:
        import shutil
        for path, is_temp in cloned_paths:
            if is_temp and path and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


def publish_handler(
        release_notes_content: str,
        release_version: str,
        docs_access_token: str,
        docs_repo_url: str,
) -> Tuple[str, str]:
    """Handle the publish button click."""
    if not release_notes_content or not release_notes_content.strip():
        return ("❌ Please generate release notes first before publishing.", "")
    if not release_version or not release_version.strip():
        return ("❌ Please provide a release version (e.g., 1.15.0).", "")

    return publish_release_notes(
        release_notes_content=release_notes_content,
        version=release_version,
        access_token=docs_access_token or None,
        docs_repo_url=docs_repo_url or None,
    )


HEADER_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "banner.png")

css = """
#banner-img img { width: 100% !important; height: auto !important; object-fit: cover; }
#banner-img { width: 100% !important; }
#banner-img .image-container button { display: none !important; }
#banner-img .icon-buttons { display: none !important; }
"""

with gr.Blocks(title="AI Release Notes Generator", css=css) as demo:
    if os.path.exists(HEADER_IMAGE_PATH):
        gr.Image(value=HEADER_IMAGE_PATH, show_label=False, interactive=False, container=False, elem_id="banner-img")

    with gr.Row():
        repo_url_or_path = gr.Textbox(
            label="Repository URLs or Local Paths (one per line)",
            placeholder="https://github.com/org/repo1.git\nhttps://github.com/org/repo2.git\n\nOptional per-line format: URL | branch | token",
            lines=4,
        )
    with gr.Row():
        access_token = gr.Textbox(
            label="Shared Access Token (optional, applies to all repos unless overridden per-line)",
            placeholder="ghp_xxxxxxxxxxxx",
            type="password",
        )
    with gr.Row():
        branch_or_tag = gr.Textbox(
            label="Shared Branch or Tag (optional, applies to all repos unless overridden per-line)",
            placeholder="main, develop, or v1.2.3",
        )
    gr.Markdown(
        "*Tip: Enter multiple repos (one per line) to generate combined release notes. "
        "Similar commits across repos are automatically deduplicated. "
        "Per-line format: `URL | branch | token`*"
    )
    with gr.Row():
        # ⬇️ Gradio 6: use DateTime for date-only picker
        start_date = gr.DateTime(label="Start Date", include_time=False, type="string")
        end_date = gr.DateTime(label="End Date", include_time=False, type="string")

    gr.Markdown("### Release Notes Options")
    with gr.Row():
        use_ai = gr.Checkbox(label="Use AI", value=True)
 
    with gr.Column(visible=True) as ai_options_col:
        with gr.Row():
            audience = gr.Dropdown(
                label="Audience",
                choices=["engineering", "customer"],
                value="engineering",
            )
        extra_context = gr.Textbox(
            label="Additional Context for AI (optional)",
            placeholder="e.g., Emphasize security fixes and performance improvements for enterprise users.",
            lines=2,
        )
        gr.Markdown("### LLM Settings")
        gr.Markdown("LLM: Ollama")
 
    use_ai.change(fn=lambda v: gr.Column(visible=v), inputs=use_ai, outputs=ai_options_col)
 
    generate_btn = gr.Button("Generate", variant="primary")
 
    status = gr.Textbox(label="Status", interactive=False)
    notes = gr.Markdown(label="Release Notes (Preview)")
 
    # Event binding remains valid in Gradio 6
    generate_btn.click(
        fn=generate_handler,
        inputs=[
            repo_url_or_path, access_token, branch_or_tag, start_date, end_date,
            use_ai, audience, extra_context,
        ],
        outputs=[status, notes],
    )

    gr.Markdown("---")
    gr.Markdown("### Publish Release Notes to Documentation")
    gr.Markdown(
        "*Publish the generated release notes above to the "
        "documentation repository (staging branch).*"
    )
    with gr.Row():
        release_version = gr.Textbox(
            label="Release Version",
            placeholder="e.g., 1.15.0",
        )
        docs_access_token = gr.Textbox(
            label="Git Access Token",
            placeholder="ghp_xxxxxxxxxxxx",
            type="password",
        )
    with gr.Row():
        docs_repo_url = gr.Textbox(
            label="Documentation Repo URL",
            placeholder="https://github.com/org/docs-repo.git",
        )

    publish_btn = gr.Button("Publish to Staging", variant="secondary")

    publish_status = gr.Textbox(label="Publish Status", interactive=False)
    publish_log = gr.Textbox(label="Publish Log", interactive=False, lines=10)

    publish_btn.click(
        fn=publish_handler,
        inputs=[notes, release_version, docs_access_token, docs_repo_url],
        outputs=[publish_status, publish_log],
    )

if __name__ == "__main__":
    # In Gradio 6, set the theme in launch(), not in Blocks(...)
    demo.launch(theme=gr.themes.Soft())