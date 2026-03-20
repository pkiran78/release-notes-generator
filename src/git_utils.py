import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

def _run_git(args, cwd=None) -> str:
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git error: {' '.join(args)}\n{e.stderr.strip()}")

def _is_git_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))

def normalize_date_value(d) -> Optional[str]:
    """
    Accepts gradio Date (date|str|None). Returns 'YYYY-MM-DD' or None.
    """
    if d is None or d == "":
        return None
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        # Attempt parsing flexible user inputs
        try:
            return datetime.fromisoformat(d).strftime("%Y-%m-%d")
        except Exception:
            # naive fallback: assume correct format
            return d
    return None

def clone_or_use_repo(repo_url_or_path: str, depth: str = "0") -> Tuple[str, bool]:
    """
    If local git repo, return path,False. Otherwise clone to temp and return path,True.
    Set depth="1" for shallow clone (faster) or "0" for full history.
    """
    if os.path.exists(repo_url_or_path) and _is_git_repo(repo_url_or_path):
        return os.path.abspath(repo_url_or_path), False

    tmpdir = tempfile.mkdtemp(prefix="rn-ollama-")
    try:
        clone_cmd = ["clone", repo_url_or_path, tmpdir]
        if depth and depth != "0":
            clone_cmd = ["clone", f"--depth={depth}", repo_url_or_path, tmpdir]
        _run_git(clone_cmd)
        return tmpdir, True
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

def checkout_ref(repo_path: str, ref: Optional[str]) -> None:
    if ref and ref.strip():
        # Fetch branches & tags, then checkout
        _run_git(["fetch", "--all", "--tags", "--prune"], cwd=repo_path)
        _run_git(["checkout", ref], cwd=repo_path)

def get_commits(repo_path: str, since: Optional[str], until: Optional[str]) -> List[Dict]:
    """
    Returns a list of commits dicts with: hash, author, email, date, subject, body.
    Dates: 'YYYY-MM-DD' strings or None.
    """
    pretty = "%H%x1f%an%x1f%ae%x1f%ad%x1f%s%x1f%b%x1e"
    args = ["log", f"--pretty=format:{pretty}", "--date=short"]
    if since:
        args.append(f"--since={since} 00:00:00")
    if until:
        args.append(f"--until={until} 23:59:59")

    out = _run_git(args, cwd=repo_path)
    commits = []
    if not out:
        return commits
    for rec in out.split("\x1e"):
        rec = rec.strip()
        if not rec:
            continue
        parts = rec.split("\x1f")
        # hash, author, email, date, subject, body
        while len(parts) < 6:
            parts.append("")
        commits.append({
            "hash": parts[0],
            "author": parts[1],
            "email": parts[2],
            "date": parts[3],
            "subject": parts[4],
            "body": (parts[5] or "").strip(),
        })
    return commits


def _normalize_subject(subject: str) -> str:
    """Strip conventional-commit prefix, scope, PR numbers, and lower-case for comparison."""
    s = subject.strip()
    # remove conventional prefix like 'feat(scope):' or 'fix!:'
    s = re.sub(r'^\w+(\([^)]*\))?!?:\s*', '', s)
    # remove trailing PR refs like (#123)
    s = re.sub(r'\s*\(#\d+\)\s*$', '', s)
    return s.lower().strip()


def _subjects_are_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Return True if two commit subjects are similar enough to be the same feature."""
    na, nb = _normalize_subject(a), _normalize_subject(b)
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def deduplicate_commits(commits: List[Dict], similarity_threshold: float = 0.75) -> List[Dict]:
    """
    Deduplicate commits that have similar subjects across multiple repos.
    Keeps the first occurrence and tags it with all source repos.
    """
    deduped: List[Dict] = []
    for commit in commits:
        found_duplicate = False
        for existing in deduped:
            if _subjects_are_similar(commit["subject"], existing["subject"], similarity_threshold):
                # Merge repo sources
                repos = existing.get("source_repos", set())
                repos.update(commit.get("source_repos", set()))
                existing["source_repos"] = repos
                found_duplicate = True
                break
        if not found_duplicate:
            deduped.append(commit)
    return deduped


def get_commits_multi_repo(
    repo_entries: List[Dict],
    since: Optional[str],
    until: Optional[str],
    depth: str = "0",
) -> Tuple[List[Dict], List[str], List[Tuple[str, bool]]]:
    """
    Fetch commits from multiple repos, tag each commit with its source repo,
    and deduplicate similar commits across repos.

    Parameters
    ----------
    repo_entries : list of dict
        Each dict has keys: 'url' (repo URL or path), 'branch' (optional ref),
        and 'token' (optional access token).
    since, until : date strings
    depth : clone depth

    Returns
    -------
    (deduped_commits, errors, cloned_paths)
        cloned_paths is a list of (path, is_temp) for cleanup.
    """
    all_commits: List[Dict] = []
    errors: List[str] = []
    cloned_paths: List[Tuple[str, bool]] = []

    for entry in repo_entries:
        url = entry["url"].strip()
        branch = entry.get("branch", "").strip()
        token = entry.get("token", "").strip()

        if not url:
            continue

        # Inject token into URL if provided
        if token:
            url = re.sub(
                r'^(https?://)',
                lambda m: f"{m.group(1)}{token}@",
                url,
            )

        repo_label = entry["url"].strip().rstrip("/").rsplit("/", 1)[-1].replace(".git", "")

        try:
            repo_path, is_temp = clone_or_use_repo(url, depth=depth)
            cloned_paths.append((repo_path, is_temp))
            checkout_ref(repo_path, branch)
            commits = get_commits(repo_path, since, until)
            for c in commits:
                c["source_repos"] = {repo_label}
            all_commits.extend(commits)
        except Exception as e:
            errors.append(f"{repo_label}: {e}")

    # Sort all commits by date descending before dedup
    all_commits.sort(key=lambda c: c.get("date", ""), reverse=True)
    deduped = deduplicate_commits(all_commits)

    # Convert source_repos sets to sorted lists for JSON serialization
    for c in deduped:
        repos = c.get("source_repos", set())
        c["source_repos"] = sorted(repos) if isinstance(repos, set) else repos

    return deduped, errors, cloned_paths