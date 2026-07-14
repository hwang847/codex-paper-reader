#!/usr/bin/env python3
"""Find a local paper PDF by copied title, alias, arXiv id, or filename."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from build_paper_index import workspace_pdfs


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def index_inputs(root: Path) -> list[Path]:
    paths = workspace_pdfs(root)
    paths.extend(
        path
        for path in (
            root / "references" / "references.bib",
            root / "references" / "source_registry.jsonl",
            root / "references" / "organization_rules.json",
        )
        if path.exists()
    )
    return paths


def indexed_pdf_paths(index_path: Path) -> set[str]:
    """Return the local PDF paths recorded by a valid generated index."""
    paths: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        value = item.get("path")
        if not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_absolute():
            paths.add(value)
    return paths


def index_is_stale(root: Path, index_path: Path) -> bool:
    if not index_path.exists():
        return True
    root = root.resolve()
    try:
        indexed_paths = indexed_pdf_paths(index_path)
        current_paths = {str(path.relative_to(root)) for path in workspace_pdfs(root)}
        if indexed_paths != current_paths:
            return True
        index_mtime = index_path.stat().st_mtime
        return any(path.stat().st_mtime > index_mtime for path in index_inputs(root))
    except (OSError, json.JSONDecodeError):
        return True


def load_index(root: Path, index_path: Path) -> list[dict]:
    if index_is_stale(root, index_path):
        script_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            [sys.executable, str(script_dir / "paper_workflow.py"), "--root", str(root), "refresh"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown refresh error"
            raise RuntimeError(f"could not refresh the literature index: {detail}")
    return [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(query: str, item: dict) -> float:
    q = normalize(query)
    aliases = item.get("normalized_aliases") or [normalize(item.get("title", ""))]
    best = 0.0
    for alias in aliases:
        if not alias:
            continue
        if q == alias:
            best = max(best, 1.0)
        elif q in alias or alias in q:
            best = max(best, 0.94)
        else:
            best = max(best, difflib.SequenceMatcher(None, q, alias).ratio())
    return best


def item_locator(item: dict) -> str:
    if item.get("path"):
        return str(item["path"])
    sources = item.get("sources")
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        return str(sources[0].get("locator") or "<no-local-pdf>")
    return "<no-local-pdf>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Find a paper in references/paper_index.jsonl.")
    parser.add_argument("query", help="copied title, method name, arXiv id, or filename")
    parser.add_argument("--root", default=".", help="literature workspace root")
    parser.add_argument("--index", default="references/paper_index.jsonl", help="JSONL index path")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    index = load_index(root, root / args.index)
    matches = sorted(
        ((score(args.query, item), item) for item in index),
        key=lambda pair: pair[0],
        reverse=True,
    )[: args.limit]
    matches = [{"score": round(value, 4), **item} for value, item in matches if value >= 0.45]

    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
    else:
        for item in matches:
            print(f"{item['score']:.4f}\t{item_locator(item)}\t{item['title']}")
    if matches:
        return 0
    print(f"No local paper matched {args.query!r}. Check the copied title or import the PDF first.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
