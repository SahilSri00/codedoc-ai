"""
tracker.py — Diff-aware file change tracking for CodeDoc-AI.

Stores SHA-256 content hashes of processed files in a local manifest
(``.codedoc-ai/manifest.json``). On subsequent runs with ``--changed-only``,
files whose hash hasn't changed are skipped — saving time and LLM API calls.

Two tracking modes:
1. **Hash-based** (default): Works everywhere, even without git.
   Compares current file content hash against the stored manifest.
2. **Git-based** (``--git-diff``): Uses ``git diff`` to find changed files.
   Faster on large repos, but requires a git repository.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Manifest location
# ---------------------------------------------------------------------------
MANIFEST_DIR = Path(__file__).resolve().parent.parent.parent / ".codedoc-ai"
MANIFEST_PATH = MANIFEST_DIR / "manifest.json"


def _ensure_manifest_dir() -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------

def hash_file(path: Path) -> str:
    """Compute a SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def _load_manifest() -> Dict[str, dict]:
    """
    Load the manifest file. Returns a dict of:
    ``{ "relative/path.py": {"hash": "abc123...", "command": "generate"} }``
    """
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_manifest(manifest: Dict[str, dict]) -> None:
    """Persist the manifest to disk."""
    _ensure_manifest_dir()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def mark_processed(file_path: Path, command: str = "generate") -> None:
    """
    Record that *file_path* was just processed by *command*.
    Stores the current content hash so future runs can detect changes.
    """
    manifest = _load_manifest()
    key = str(file_path.resolve())
    manifest[key] = {
        "hash": hash_file(file_path),
        "command": command,
    }
    _save_manifest(manifest)


def has_changed(file_path: Path, command: str = "generate") -> bool:
    """
    Return True if *file_path* has changed since it was last processed
    by *command* (or if it has never been processed).
    """
    manifest = _load_manifest()
    key = str(file_path.resolve())
    entry = manifest.get(key)

    if entry is None:
        return True  # Never processed

    if entry.get("command") != command:
        return True  # Processed by a different command

    current_hash = hash_file(file_path)
    return current_hash != entry.get("hash")


# ---------------------------------------------------------------------------
# Git-based change detection
# ---------------------------------------------------------------------------

def get_git_changed_files(repo_root: Path, ref: str = "HEAD") -> Optional[Set[str]]:
    """
    Use ``git diff`` to find files that have changed relative to *ref*.

    Returns:
        A set of absolute file paths that have changed, or None if git
        is not available or the directory is not a git repo.
    """
    try:
        # Unstaged changes + staged changes + untracked files
        result_diff = subprocess.run(
            ["git", "diff", "--name-only", ref],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        result_staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        result_untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )

        changed: Set[str] = set()
        for result in (result_diff, result_staged, result_untracked):
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    if line.strip():
                        abs_path = str((repo_root / line.strip()).resolve())
                        changed.add(abs_path)

        return changed

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None  # git not available


# ---------------------------------------------------------------------------
# Filtering helper
# ---------------------------------------------------------------------------

def filter_changed_files(
    paths: List[Path],
    command: str = "generate",
    git_diff: bool = False,
    repo_root: Optional[Path] = None,
) -> List[Path]:
    """
    Filter *paths* to only those that have changed since last run.

    Args:
        paths: List of file paths to check.
        command: The command name (generate, inject, index) for manifest tracking.
        git_diff: If True, use git diff instead of manifest hashes.
        repo_root: Required when git_diff=True.

    Returns:
        Filtered list of paths that need processing.
    """
    if git_diff and repo_root:
        git_changed = get_git_changed_files(repo_root)
        if git_changed is not None:
            return [p for p in paths if str(p.resolve()) in git_changed]
        # Fallback to hash-based if git is unavailable
        print("[WARN] Git not available, falling back to hash-based tracking")

    return [p for p in paths if has_changed(p, command=command)]
