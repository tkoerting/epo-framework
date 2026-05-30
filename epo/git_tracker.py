"""
EPO Git Tracker -- Extracts edit signals from git history.

Identifies Claude Code commits (by Co-Authored-By tag) and measures
how much the user changed Claude's output afterward.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from epo.edit_distance import calculate_edit_score


@dataclass
class FileEdit:
    """A single file that Claude wrote and the user subsequently edited."""
    file_path: str
    original_content: str  # What Claude wrote
    final_content: str     # What the user changed it to
    edit_score: float      # 0.0 = kept as-is, 1.0 = fully rewritten


@dataclass
class SessionAnalysis:
    """Analysis of one Claude Code session."""
    claude_commit: str
    claude_message: str
    comparison_ref: str  # HEAD or next human commit
    file_edits: list[FileEdit] = field(default_factory=list)
    avg_edit_score: float = 0.0
    files_unchanged: int = 0
    files_modified: int = 0
    files_deleted: int = 0


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        cwd=cwd or Path.cwd(),
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)}: {stderr}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def get_project_root(cwd: Path | None = None) -> Path:
    """Find the git repository root."""
    root = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(root)


def find_claude_commits(limit: int = 50, cwd: Path | None = None) -> list[dict]:
    """
    Find commits authored or co-authored by Claude.

    Returns list of {hash, message, date} dicts, newest first.
    """
    log_output = _run_git([
        "log", f"-{limit}",
        "--grep=Co-Authored-By.*Claude", "--grep=Co-authored-by.*Claude",
        "--format=%H|%s|%ai",
    ], cwd=cwd)

    if not log_output:
        return []

    commits = []
    for line in log_output.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "date": parts[2],
            })
    return commits


def find_next_human_commit(claude_hash: str, cwd: Path | None = None) -> str | None:
    """
    Find the next commit after a Claude commit that is NOT by Claude.
    Returns the commit hash, or None if the Claude commit is the latest.
    """
    try:
        log_output = _run_git([
            "log", "--reverse", "--format=%H|%s",
            f"{claude_hash}..HEAD",
        ], cwd=cwd)
    except RuntimeError:
        return None

    if not log_output:
        return None

    for line in log_output.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2:
            commit_hash = parts[0]
            # Check if this commit is NOT by Claude
            commit_body = _run_git(["log", "-1", "--format=%b", commit_hash], cwd=cwd)
            if "Co-Authored-By" not in commit_body and "Co-authored-by" not in commit_body:
                return commit_hash

    return None


def find_next_commit(commit_hash: str, cwd: Path | None = None) -> str | None:
    """
    Find the immediately next commit after the given one (any author).
    Returns the commit hash, or None if it's the latest commit.
    """
    try:
        log_output = _run_git([
            "log", "--reverse", "--format=%H",
            f"{commit_hash}..HEAD", "--first-parent",
        ], cwd=cwd)
    except RuntimeError:
        return None

    if not log_output:
        return None

    return log_output.splitlines()[0].strip()


def get_files_in_commit(commit_hash: str, cwd: Path | None = None) -> list[str]:
    """Get list of files changed in a specific commit."""
    output = _run_git(["diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash], cwd=cwd)
    if not output:
        return []
    return [f for f in output.splitlines() if f and not f.startswith(".")]


def get_file_at_commit(file_path: str, commit_hash: str, cwd: Path | None = None) -> str | None:
    """Get file content at a specific commit. Returns None if file doesn't exist."""
    try:
        return _run_git(["show", f"{commit_hash}:{file_path}"], cwd=cwd)
    except RuntimeError:
        return None


def analyze_session(claude_hash: str, compare_to: str = "HEAD", cwd: Path | None = None) -> SessionAnalysis:
    """
    Analyze a Claude Code session by comparing what Claude wrote
    to what exists now (or at a later commit).

    Args:
        claude_hash: The commit hash of Claude's work
        compare_to: What to compare against (default: HEAD)
        cwd: Working directory
    """
    message = _run_git(["log", "-1", "--format=%s", claude_hash], cwd=cwd)
    files = get_files_in_commit(claude_hash, cwd=cwd)

    analysis = SessionAnalysis(
        claude_commit=claude_hash[:8],
        claude_message=message,
        comparison_ref=compare_to[:8] if len(compare_to) > 8 else compare_to,
    )

    edits = []
    for file_path in files:
        # Skip non-text files
        if any(file_path.endswith(ext) for ext in [".png", ".jpg", ".gif", ".ico", ".woff", ".ttf", ".pyc"]):
            continue

        original = get_file_at_commit(file_path, claude_hash, cwd=cwd)
        if original is None:
            continue

        final = get_file_at_commit(file_path, compare_to, cwd=cwd)
        if final is None:
            analysis.files_deleted += 1
            continue

        score = calculate_edit_score(original, final)
        edit = FileEdit(
            file_path=file_path,
            original_content=original,
            final_content=final,
            edit_score=score,
        )
        edits.append(edit)

        if score == 0.0:
            analysis.files_unchanged += 1
        else:
            analysis.files_modified += 1

    analysis.file_edits = edits
    if edits:
        analysis.avg_edit_score = round(
            sum(e.edit_score for e in edits) / len(edits), 3
        )

    return analysis


def analyze_latest_sessions(max_sessions: int = 5, cwd: Path | None = None) -> list[SessionAnalysis]:
    """
    Find recent Claude commits and analyze each one.
    Compares each Claude commit against the next commit (not HEAD).
    """
    commits = find_claude_commits(limit=max_sessions, cwd=cwd)
    results = []
    for commit in commits:
        try:
            next_ref = find_next_commit(commit["hash"], cwd=cwd) or "HEAD"
            analysis = analyze_session(commit["hash"], compare_to=next_ref, cwd=cwd)
            results.append(analysis)
        except RuntimeError:
            continue
    return results
