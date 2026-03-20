"""Publisher module — Publishes generated release notes to a documentation repo.

Workflow:
1. Clone documentation repo (or use local copy)
2. Checkout staging branch
3. Create docs/release_notes/v{version_folder}/ directory
4. Create .nav and index.md inside the version folder
5. Update the parent docs/release_notes/.nav to include the new version at the top
6. Update TAG in Makefile
7. Commit and push to staging branch
"""

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Optional, Tuple

# Default repo URL for documentation repo (optional)
DOCS_REPO_URL = os.getenv("DOCS_REPO_URL", "").strip()

# Header used in .nav files
NAV_COPYRIGHT_HEADER = """# custom navigation order and structure
# (update this when adding/removing/moving markdown files)
# --------------------------------------------------------
"""


def _run_git(args: list, cwd: str) -> str:
    """Run a git command and return stdout."""
    cmd = ["git"] + args
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _version_to_folder_name(version: str) -> str:
    """
    Convert version string to folder name format.
    e.g. '1.15.0' -> 'v1_15_0', 'v1.15.0' -> 'v1_15_0'
    """
    v = version.strip().lstrip("vV")
    return "v" + v.replace(".", "_")


def _version_to_display(version: str) -> str:
    """
    Convert version string to display format for .nav.
    e.g. '1.15.0' -> 'V1.15.0', 'v1.15.0' -> 'V1.15.0'
    """
    v = version.strip().lstrip("vV")
    return "V" + v


def _version_to_tag(version: str) -> str:
    """
    Convert version string to TAG format for Makefile.
    e.g. 'v1.15.0' -> '1.15.0'
    """
    return version.strip().lstrip("vV")


def _create_version_nav(version_dir: str) -> None:
    """Create the .nav file inside the version folder."""
    nav_content = NAV_COPYRIGHT_HEADER + "\nnav:\n    - index.md\n"
    with open(os.path.join(version_dir, ".nav"), "w", encoding="utf-8") as f:
        f.write(nav_content)


def _post_process_release_notes(content: str, version: str) -> str:
    """
    Post-process AI-generated release notes to match documentation format:
    1. Ensure title is the version (# vX.Y.Z)
    2. Add '## Release Date' section with today's date right after the title
    3. Remove empty sections (## heading with no content before next heading)
    """
    display_version = _version_to_display(version).replace("V", "v")
    lines = content.strip().splitlines()
    result_lines = []

    # Step 1: Process title — ensure first # heading is the version
    i = 0
    title_found = False
    while i < len(lines):
        line = lines[i]
        if not title_found and line.startswith("# ") and not line.startswith("## "):
            result_lines.append(f"# {display_version}")
            title_found = True
            i += 1
            # Skip blank lines after title
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            # Step 2: Insert Release Date section
            today = datetime.now().strftime("%B %d, %Y")
            result_lines.append("")
            result_lines.append("")
            result_lines.append("## Release Date")
            result_lines.append("")
            result_lines.append(f"**Release Date:** {today}")
            result_lines.append(" ")
            continue
        result_lines.append(line)
        i += 1

    # If no title was found, prepend one with release date
    if not title_found:
        today = datetime.now().strftime("%B %d, %Y")
        header = [
            f"# {display_version}",
            "",
            "",
            "## Release Date",
            "",
            f"**Release Date:** {today}",
            " ",
        ]
        result_lines = header + result_lines

    # Step 3: Remove empty sections
    # A section is empty if a ## heading is followed only by blank lines until the next ## heading or EOF
    cleaned_lines = []
    j = 0
    all_lines = result_lines
    while j < len(all_lines):
        line = all_lines[j]
        if line.startswith("## "):
            # Look ahead to see if this section has any content
            section_lines = [line]
            k = j + 1
            while k < len(all_lines) and not all_lines[k].startswith("## ") and not all_lines[k].startswith("# "):
                section_lines.append(all_lines[k])
                k += 1
            # Check if section has non-blank content (beyond the heading itself)
            has_content = any(l.strip() for l in section_lines[1:])
            if has_content:
                cleaned_lines.extend(section_lines)
            j = k
        else:
            cleaned_lines.append(line)
            j += 1

    text = "\n".join(cleaned_lines).rstrip() + "\n"
    return text


def _create_index_md(version_dir: str, version: str, release_notes_content: str) -> None:
    """Create the index.md file inside the version folder with the release notes."""
    processed = _post_process_release_notes(release_notes_content, version)
    with open(os.path.join(version_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(processed)


def _update_parent_nav(release_notes_dir: str, version: str) -> None:
    """
    Update the parent docs/release_notes/.nav to include the new version at the top.
    Inserts the new version entry right after the 'nav:' line (first position).
    """
    nav_path = os.path.join(release_notes_dir, ".nav")
    folder_name = _version_to_folder_name(version)
    display_name = _version_to_display(version)
    new_entry = f"    - {display_name}: {folder_name}"

    with open(nav_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Check if this version already exists
    for line in lines:
        if folder_name in line:
            return  # Already present, skip

    # Find the 'nav:' line and insert after it
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and line.strip() == "nav:":
            new_lines.append(new_entry + "\n")
            inserted = True

    with open(nav_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _update_makefile_tag(repo_dir: str, version: str) -> None:
    """Update the TAG variable in the Makefile."""
    makefile_path = os.path.join(repo_dir, "Makefile")
    tag_value = _version_to_tag(version)

    with open(makefile_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace TAG = x.y.z with new version
    updated = re.sub(
        r'^(TAG\s*=\s*).*$',
        f'TAG           = {tag_value}',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    if updated == content:
        raise RuntimeError("Could not find TAG variable in Makefile to update.")

    with open(makefile_path, "w", encoding="utf-8") as f:
        f.write(updated)


def publish_release_notes(
    release_notes_content: str,
    version: str,
    access_token: Optional[str] = None,
    docs_repo_url: Optional[str] = None,
    commit_message: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Publish release notes to documentation repo.

    Parameters
    ----------
    release_notes_content : str
        The markdown release notes content to publish.
    version : str
        Release version (e.g., '1.15.0' or 'v1.15.0').
    access_token : str, optional
        Git access token for cloning/pushing. Injected into the repo URL.
    docs_repo_url : str, optional
        Override the default documentation repo URL.
    commit_message : str, optional
        Custom commit message. Defaults to 'Add release notes for vX.Y.Z'.

    Returns
    -------
    (status, details) : tuple of str
        Status message and detailed log of actions taken.
    """
    if not release_notes_content or not release_notes_content.strip():
        return ("❌ No release notes content to publish.", "")

    if not version or not version.strip():
        return ("❌ Please provide a release version.", "")

    repo_url = (docs_repo_url or DOCS_REPO_URL).strip()
    if not repo_url:
        return (
            "❌ Documentation Repo URL is required.",
            "Set DOCS_REPO_URL env var or provide a URL in the UI.",
        )
    version = version.strip()
    folder_name = _version_to_folder_name(version)
    display_version = _version_to_display(version)
    tag_value = _version_to_tag(version)

    # Inject token into URL if provided
    if access_token and access_token.strip():
        token = access_token.strip()
        repo_url = re.sub(
            r'^(https?://)',
            lambda m: f"{m.group(1)}{token}@",
            repo_url,
        )

    log_lines = []
    tmpdir = None

    try:
        # Step 1: Clone the repo
        tmpdir = tempfile.mkdtemp(prefix="rn-publish-")
        log_lines.append(f"📦 Cloning documentation repo to temp directory...")
        _run_git(["clone", repo_url, tmpdir + "/repo"], cwd=tmpdir)
        repo_dir = os.path.join(tmpdir, "repo")
        log_lines.append(f"✅ Cloned successfully.")

        # Step 2: Checkout staging branch
        log_lines.append(f"🔀 Checking out staging branch...")
        _run_git(["checkout", "staging"], cwd=repo_dir)
        _run_git(["pull", "origin", "staging"], cwd=repo_dir)
        log_lines.append(f"✅ On staging branch (up to date).")

        # Step 3: Create version folder
        release_notes_dir = os.path.join(repo_dir, "docs", "release_notes")
        version_dir = os.path.join(release_notes_dir, folder_name)

        if os.path.exists(version_dir):
            log_lines.append(f"⚠️ Folder {folder_name} already exists. Overwriting files...")
        else:
            os.makedirs(version_dir)
            log_lines.append(f"📁 Created folder: docs/release_notes/{folder_name}/")

        # Step 4: Create .nav file in version folder
        _create_version_nav(version_dir)
        log_lines.append(f"📄 Created docs/release_notes/{folder_name}/.nav")

        # Step 5: Create index.md with release notes
        _create_index_md(version_dir, version, release_notes_content)
        log_lines.append(f"📄 Created docs/release_notes/{folder_name}/index.md")

        # Read back the processed index.md content for display
        index_md_path = os.path.join(version_dir, "index.md")
        with open(index_md_path, "r", encoding="utf-8") as f:
            index_md_content = f.read()
        log_lines.append(f"\n--- docs/release_notes/{folder_name}/index.md ---")
        log_lines.append(index_md_content)
        log_lines.append("--- end of index.md ---\n")

        # Step 6: Update parent .nav
        _update_parent_nav(release_notes_dir, version)
        log_lines.append(f"📝 Updated docs/release_notes/.nav (added {display_version})")

        # Step 7: Update Makefile TAG
        _update_makefile_tag(repo_dir, version)
        log_lines.append(f"📝 Updated Makefile TAG = {tag_value}")

        # Step 8: Git add, commit, push
        msg = commit_message or f"Add release notes for {display_version}"
        _run_git(["add", "."], cwd=repo_dir)

        # Check if there are changes to commit
        status_output = _run_git(["status", "--porcelain"], cwd=repo_dir)
        if not status_output:
            return ("⚠️ No changes detected. Release notes may already be published.", "\n".join(log_lines))
        
        # TODO: Uncomment the following lines to commit and push
        # _run_git(["commit", "-m", msg], cwd=repo_dir)
        # log_lines.append(f"💾 Committed: {msg}")

        # _run_git(["push", "origin", "staging"], cwd=repo_dir)
        # log_lines.append(f"🚀 Pushed to staging branch!")

        log_lines.append(f"📂 Repo cloned at: {repo_dir}")
        log_lines.append(f"Run 'git status' and 'git diff --cached' in the above path to inspect changes.")

        status = f"✅ Changes prepared for {display_version} (commit/push skipped for testing)."
        return (status, "\n".join(log_lines))

    except Exception as e:
        log_lines.append(f"❌ Error: {e}")
        return (f"❌ Publish failed: {e}", "\n".join(log_lines))

    finally:
        # NOTE: Not cleaning up temp dir so you can inspect changes
        # if tmpdir and os.path.isdir(tmpdir):
        #     shutil.rmtree(tmpdir, ignore_errors=True)
        pass
