#!/usr/bin/env python3
"""Scan release files and reachable history for common secret/privacy leaks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DENY = (
    "/" + "Users/",
    "wang" + "haoran",
    "Desktop/" + "text2sql",
    ".codex/" + "RT" + "K.md",
    "@/" + "Users/",
)
TOKEN_PREFIXES = (
    "gh" + "o_",
    "gh" + "p_",
    "github" + "_pat_",
    "sk" + "-",
    "xox" + "b-",
    "xox" + "p-",
)
PRIVATE_KEY_MARKER = "-----BEGIN " + "PRIVATE KEY-----"
PRIVATE_PATH_RE = re.compile(r"/(?:Users|home|private|var/folders)/", re.IGNORECASE)
URL_CREDENTIAL_RE = re.compile(r"https?://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)


def iter_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        ignored = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        return [
            path
            for path in ROOT.rglob("*")
            if path.is_file() and not any(part in ignored for part in path.parts)
        ]
    names = dict.fromkeys(result.stdout.decode("utf-8").split("\0"))
    return [ROOT / name for name in names if name and (ROOT / name).is_file()]


def release_leaks(text: str) -> list[str]:
    leaks = [needle for needle in DENY if needle in text]
    leaks.extend(prefix for prefix in TOKEN_PREFIXES if prefix in text)
    if PRIVATE_KEY_MARKER in text:
        leaks.append("private-key marker")
    if PRIVATE_PATH_RE.search(text):
        leaks.append("private-path pattern")
    if URL_CREDENTIAL_RE.search(text):
        leaks.append("URL credential")
    return leaks


def history_commits() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--all"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return [commit for commit in result.stdout.splitlines() if commit]


def main() -> int:
    leaks: list[str] = []
    for path in iter_files():
        data = path.read_bytes()
        if b"\0" in data:
            leaks.append(f"{path.relative_to(ROOT)} is binary")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            leaks.append(f"{path.relative_to(ROOT)} is not UTF-8 text")
            continue
        for leak in release_leaks(text):
            leaks.append(f"{path.relative_to(ROOT)} contains {leak!r}")
    for commit in history_commits():
        result = subprocess.run(
            ["git", "grep", "-Ilz", "", commit],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode not in (0, 1):
            leaks.append(f"could not scan history {commit[:12]}")
            continue
        for object_name in filter(None, result.stdout.split("\0")):
            blob = subprocess.run(
                ["git", "show", object_name],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if blob.returncode != 0:
                leaks.append(f"could not read history object {object_name}")
                continue
            if b"\0" in blob.stdout:
                continue
            text = blob.stdout.decode("utf-8", errors="ignore")
            for leak in release_leaks(text):
                leaks.append(f"history {object_name} contains {leak!r}")
    if leaks:
        print("\n".join(leaks))
        return 1
    print("privacy scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
