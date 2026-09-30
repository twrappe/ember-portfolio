import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _iter_repo_text_files():
    skip_dirs = {
        ".git",
        "venv",
        "node_modules",
        "playwright-report",
        "test-results",
        "__pycache__",
        "logs",
        "data",
    }
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".yml", ".yaml", ".txt", ".json", ".ps1"}:
            continue
        yield path


def test_env_file_is_gitignored():
    """Real-world failure prevented: accidental commit of local OAuth tokens to source control."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in {line.strip() for line in gitignore.splitlines()}


def test_ci_workflows_do_not_hardcode_tokens():
    """Real-world failure prevented: static tokens in workflow YAML leak into logs and forks."""
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    hardcoded = []
    pattern = re.compile(r"OURA_(ACCESS|REFRESH)_TOKEN\s*:\s*['\"]?[A-Za-z0-9_-]{20,}")

    for wf in workflow_dir.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            if "${{ secrets." not in m.group(0):
                hardcoded.append(f"{wf}:{m.group(0)}")

    assert not hardcoded, "\n".join(hardcoded)


def test_repo_text_has_no_bearer_token_literals():
    """Real-world failure prevented: OAuth bearer tokens committed or echoed in scripts/docs."""
    token_pattern = re.compile(r"Bearer\s+[A-Za-z0-9_-]{20,}")
    hits = []

    for path in _iter_repo_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in token_pattern.finditer(text):
            hits.append(f"{path.relative_to(REPO_ROOT)}:{match.group(0)[:24]}...")

    assert not hits, "\n".join(hits)
