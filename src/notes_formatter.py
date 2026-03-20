import re
from typing import Dict, List, Optional, Tuple

CONVENTIONAL_TYPES_ORDER = [
    "feat", "fix", "perf", "refactor", "build", "ci",
    "docs", "style", "test", "chore", "revert", "deps", "other",
]

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>\w+)(\((?P<scope>[^)]+)\))?!(?::|\s:)|^(?P<type2>\w+)(\((?P<scope2>[^)]+)\))?:"
)

def classify_commit(subject: str) -> Tuple[str, Optional[str], bool]:
    breaking = "!" in subject.split(":")[0] if ":" in subject else False
    m = CONVENTIONAL_RE.match(subject or "")
    if m:
        t = m.group("type") or m.group("type2") or "other"
        scope = m.group("scope") or m.group("scope2")
        return t.lower(), scope, breaking
    return "other", None, breaking

def format_release_notes_plain(
    commits: List[Dict],
    title: Optional[str] = None,
    group_conventional: bool = True,
    markdown: bool = True,
    include_hash: bool = True,
) -> str:
    if not commits:
        return "No commits found in the selected range."

    if markdown:
        lines = [f"# {title or 'Release Notes'}", ""]
    else:
        lines = [title or "RELEASE NOTES", ""]

    if group_conventional:
        grouped: Dict[str, List[Dict]] = {k: [] for k in CONVENTIONAL_TYPES_ORDER}
        for c in commits:
            t, scope, breaking = classify_commit(c["subject"])
            t = t if t in grouped else "other"
            c["_type"], c["_scope"], c["_breaking"] = t, scope, breaking
            grouped[t].append(c)
        sections = [(t, grouped[t]) for t in CONVENTIONAL_TYPES_ORDER if grouped[t]]
    else:
        sections = [("Changes", commits)]

    for title, items in sections:
        lines.append(f"## {title.capitalize()}" if markdown else title.upper())
        for c in items:
            scope = f"**({c.get('_scope')})** " if markdown and c.get("_scope") else (f"({c.get('_scope')}) " if c.get("_scope") else "")
            hash_part = f" ({c['hash'][:7]})" if include_hash else ""
            breaking = " **BREAKING**" if markdown and c.get("_breaking") else (" [BREAKING]" if c.get("_breaking") else "")
            repo_part = ""
            if c.get("source_repos"):
                repos = c["source_repos"]
                if isinstance(repos, (list, set)) and len(repos) > 0:
                    repo_part = f" [{', '.join(sorted(repos))}]"
            lines.append(f"- {scope}{c['subject']}{breaking}{hash_part}{repo_part} — {c['author']} · {c['date']}")
        lines.append("")

    authors = sorted({c["author"] for _, items in sections for c in (items if isinstance(items, list) else [])})
    if markdown:
        lines.append("### Contributors")
        lines.append(", ".join(authors) if authors else "_None_")
    else:
        lines.append("Contributors:")
        lines.append(", ".join(authors) if authors else "None")
    return "\n".join(lines)
