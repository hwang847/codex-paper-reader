#!/usr/bin/env python3
"""One command surface for the literature workflow skill."""

from __future__ import annotations

import argparse
import errno
import http.client
import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from build_paper_index import build_index, extract_pdf_title
from find_paper import index_is_stale, score


ARXIV_ID_RE = re.compile(r"^(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?$")
ARXIV_IN_TEXT_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?")
AMBIGUITY_MARGIN = 0.03
MIN_CONFIDENT_SCORE = 0.92
SOURCE_REGISTRY = Path("references/source_registry.jsonl")
ORGANIZATION_JOURNAL = Path("references/organization_recovery.json")
SOURCE_KINDS = {"paper", "survey", "tech_doc", "spec", "blog", "repo", "dataset", "slides", "unknown"}
LOCAL_SOURCE_TYPES = {"pdf", "doc", "html", "text", "path"}
WORKSPACE_DIRS = ("papers", "notes", "notes/assets", "references", "surveys", "surveys/sources")
ORGANIZATION_RULES = Path("references/organization_rules.json")
SURVEYS_DIR = Path("surveys")
SURVEY_SOURCES_DIR = SURVEYS_DIR / "sources"
SURVEY_MANIFEST = "manifest.json"
SURVEY_READING_PACK = "reading_pack.md"
SURVEY_DOCUMENT_SUFFIXES = {".md", ".txt", ".rst", ".html", ".htm", ".docx"}
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
WELL_KNOWN_NAT64_PREFIXES = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)

DEFAULT_ORGANIZATION_RULES = {
    "version": 1,
    "default_category": "uncategorized",
    "categories": [
        {"name": "surveys", "keywords": ["survey", "overview", "landscape", "selective overview"]},
        {
            "name": "methods",
            "keywords": [
                "method",
                "approach",
                "framework",
                "algorithm",
                "reasoning",
                "planning",
            ],
        },
        {
            "name": "agents-and-tools",
            "keywords": [
                "agent",
                "agentic",
                "multi-agent",
                "tool use",
                "tool calling",
                "workflow",
            ],
        },
        {
            "name": "training-and-alignment",
            "keywords": [
                "reinforcement learning",
                "fine-tuning",
                "fine tuning",
                "preference optimization",
                "reward",
                "alignment",
            ],
        },
        {
            "name": "retrieval-and-data",
            "keywords": [
                "retrieval",
                "retrieval-augmented",
                "rag",
                "knowledge graph",
                "database",
                "data management",
                "vector search",
            ],
        },
        {
            "name": "systems-and-infrastructure",
            "keywords": [
                "system",
                "serving",
                "distributed",
                "long context",
                "memory",
                "vector database",
                "infrastructure",
            ],
        },
        {
            "name": "benchmarks-and-evaluation",
            "keywords": [
                "benchmark",
                "dataset",
                "evaluation",
                "leaderboard",
                "challenge",
                "shared task",
            ],
        },
        {"name": "uncategorized", "keywords": []},
    ],
    "title_overrides": {},
    "category_overrides": {},
}


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def note_filename(title: str) -> str:
    title = title.strip()
    if ":" in title:
        head = title.split(":", 1)[0].strip()
        if head and len(head.split()) <= 4 and (re.search(r"[A-Z]{2,}|[-_]", head) or head[:1].isupper()):
            title = head
    return f"{normalize(title)}.html"


def entity_id(title: str) -> str:
    return Path(note_filename(title)).stem


def ensure_root(root: Path) -> None:
    if not root.exists():
        raise WorkflowError("root_missing", f"workspace root does not exist: {root}")
    if not root.is_dir():
        raise WorkflowError("root_not_dir", f"workspace root is not a directory: {root}")


def workspace_path(root: Path, path: Path | str, label: str) -> Path:
    """Resolve a managed path and reject symlink or traversal escapes."""
    resolved_root = root.resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise WorkflowError(
            "workspace_path_escape",
            f"{label} must stay inside the workspace root: {path}",
        ) from exc
    return resolved


def is_workspace_path(root: Path, path: Path) -> bool:
    try:
        workspace_path(root, path, "path")
    except WorkflowError:
        return False
    return True


def write_index(root: Path) -> list[dict]:
    root = root.resolve()
    ensure_root(root)
    bib_path = workspace_path(root, "references/references.bib", "BibTeX path")
    try:
        index = build_index(root, bib_path)
    except ValueError as exc:
        raise WorkflowError("index_build_failed", str(exc)) from exc
    rules = load_organization_rules(root)
    for item in index:
        path = str(item.get("path", ""))
        for key in (path, Path(path).name, str(item.get("title", ""))):
            override = rule_override(rules, key)
            if not override:
                continue
            original = str(item.get("title", ""))
            item["title"] = clean_organization_title(override)
            item["aliases"] = sorted({*item.get("aliases", []), original, item["title"]})
            item["normalized_aliases"] = [normalize(alias) for alias in item["aliases"]]
            item["title_source"] = "organization_rules"
            break
    output = workspace_path(root, "references/paper_index.jsonl", "paper index")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in index) + "\n",
        encoding="utf-8",
    )
    return index


def read_index(root: Path) -> list[dict]:
    root = root.resolve()
    ensure_root(root)
    index_path = workspace_path(root, "references/paper_index.jsonl", "paper index")
    if index_is_stale(root, index_path):
        write_index(root)
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError):
        write_index(root)
        lines = index_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


def find_matches(root: Path, query: str, limit: int) -> list[dict]:
    if not query.strip():
        raise WorkflowError("empty_query", "paper query is empty")
    index = read_index(root)
    matches = sorted(
        ((score(query, item), item) for item in index),
        key=lambda pair: pair[0],
        reverse=True,
    )[:limit]
    return [{"score": round(value, 4), **item} for value, item in matches if value >= 0.45]


def resolve_pdf(root: Path, query: str) -> tuple[Path, dict | None]:
    root = root.resolve()
    path = Path(query).expanduser()
    if path.exists():
        return workspace_path(root, path, "PDF source"), None
    path = root / query
    if path.exists():
        return workspace_path(root, path, "PDF source"), None
    normalized_query = normalize(query)
    if normalized_query:
        exact = []
        for item in read_index(root):
            aliases = [str(item.get("title", "")), str(item.get("entity_id", ""))]
            aliases.extend(str(alias) for alias in item.get("aliases", []) if alias)
            if normalized_query in {normalize(alias) for alias in aliases if alias}:
                exact.append(item)
        if len(exact) == 1:
            if exact[0].get("path"):
                return workspace_path(root, str(exact[0]["path"]), "indexed PDF"), exact[0]
            raise WorkflowError("no_pdf_source", f"matched entity has no local PDF source: {exact[0].get('title', query)}", exact[0])
        if len(exact) > 1:
            raise WorkflowError("ambiguous_match", "paper query is ambiguous", exact)
    matches = find_matches(root, query, 5)
    if not matches:
        raise WorkflowError("no_match", f"no paper match: {query}")
    pdf_matches = [item for item in matches if item.get("path")]
    if not pdf_matches:
        raise WorkflowError("no_pdf_source", f"matched entity has no local PDF source: {matches[0].get('title', query)}", matches[0])
    top = pdf_matches[0]
    if len(pdf_matches) > 1:
        second = pdf_matches[1]
        near_tie = top["score"] - second["score"] <= AMBIGUITY_MARGIN
        generic_query = len(re.sub(r"[^A-Za-z0-9]", "", query)) <= 4
        if top["score"] < MIN_CONFIDENT_SCORE or (top["score"] < 0.99 and (near_tie or generic_query)):
            raise WorkflowError("ambiguous_match", "paper query is ambiguous", matches)
    if not top.get("path"):
        raise WorkflowError("no_pdf_source", f"matched item has no local PDF source: {top.get('title', query)}", top)
    return workspace_path(root, str(top["path"]), "indexed PDF"), top


def item_locator(item: dict) -> str:
    if item.get("path"):
        return str(item["path"])
    if item.get("sources"):
        source = item["sources"][0]
        if isinstance(source, dict):
            return str(source.get("locator") or "<no-local-pdf>")
    return str(item.get("primary_source") or "<no-local-pdf>")


def normalize_pdf_name(name: str) -> str:
    name = Path(name).name.strip() or "paper.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    safe = re.sub(r"_+", "_", safe).strip("._")
    return safe or "paper.pdf"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for idx in range(2, 1000):
        candidate = path.with_name(f"{stem}_{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise WorkflowError("name_collision", f"too many existing files named like {path.name}")


def load_organization_rules(root: Path, rules: str | None = None) -> dict:
    path = root / (rules or ORGANIZATION_RULES)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_ORGANIZATION_RULES))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("invalid_organization_rules", f"invalid organization rules: {path}", str(exc)) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("categories"), list):
        raise WorkflowError("invalid_organization_rules", "organization rules need a categories list")
    categories = []
    for item in payload["categories"]:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            raise WorkflowError("invalid_organization_rules", "every category needs a non-empty name")
        name = str(item["name"]).strip()
        if name in {".", ".."} or Path(name).name != name:
            raise WorkflowError("invalid_organization_rules", f"category name must be one directory name: {name}")
        keywords = item.get("keywords", [])
        if not isinstance(keywords, list) or not all(isinstance(value, str) for value in keywords):
            raise WorkflowError("invalid_organization_rules", f"invalid keywords for category {item['name']}")
        requires_any = item.get("requires_any", [])
        requires_all = item.get("requires_all", [])
        if not isinstance(requires_any, list) or not all(isinstance(value, str) for value in requires_any):
            raise WorkflowError("invalid_organization_rules", f"invalid requires_any for category {item['name']}")
        if not isinstance(requires_all, list) or not all(isinstance(value, str) for value in requires_all):
            raise WorkflowError("invalid_organization_rules", f"invalid requires_all for category {item['name']}")
        categories.append(
            {
                "name": name,
                "keywords": keywords,
                "requires_any": requires_any,
                "requires_all": requires_all,
            }
        )
    payload["categories"] = categories
    payload.setdefault("default_category", "uncategorized")
    payload.setdefault("title_overrides", {})
    payload.setdefault("category_overrides", {})
    return payload


def organization_key(value: str) -> str:
    return str(value).replace("\\", "/").strip().lower()


def rule_override(rules: dict, key: str) -> str | None:
    overrides = rules.get("title_overrides", {})
    if not isinstance(overrides, dict):
        return None
    normalized = organization_key(key)
    for candidate, value in overrides.items():
        if organization_key(str(candidate)) == normalized and str(value).strip():
            return str(value).strip()
    return None


def category_override(rules: dict, item: dict, rel_path: str, title: str) -> str | None:
    overrides = rules.get("category_overrides", {})
    if not isinstance(overrides, dict):
        return None
    candidates = [rel_path, Path(rel_path).name, title, str(item.get("entity_id", ""))]
    for candidate in candidates:
        candidate_key = organization_key(candidate)
        candidate_slug = normalize(candidate)
        for key, value in overrides.items():
            if organization_key(str(key)) in {candidate_key, candidate_slug} and isinstance(value, str) and value.strip():
                return value.strip()
    return None


def clean_organization_title(title: str) -> str:
    value = clean_text(str(title))
    value = re.sub(r"\s+[†‡*]+\s*", " ", value)
    value = re.sub(r"\s+\d+(?=\s|$)", " ", value)
    return clean_text(value).strip(" ._")


def paper_filename(title: str, fallback: str) -> str:
    value = normalize(clean_organization_title(title))
    if not value:
        value = normalize(Path(fallback).stem)
    if not value:
        value = "paper"
    return f"{value[:180].rstrip('_')}.pdf"


def keyword_matches(text: str, keyword: str) -> int:
    phrase = normalize(keyword).replace("_", " ").strip()
    if not phrase:
        return 0
    normalized = normalize(text).replace("_", " ")
    if " " in phrase:
        return int(phrase in normalized)
    return int(bool(re.search(rf"\b{re.escape(phrase)}\b", normalized)))


def classify_paper(item: dict, title: str, rules: dict, rel_path: str) -> tuple[str, list[str]]:
    override = category_override(rules, item, rel_path, title)
    category_names = {str(entry["name"]) for entry in rules["categories"]}
    if override:
        if override not in category_names:
            raise WorkflowError("invalid_organization_rules", f"unknown category override: {override}")
        return override, ["override"]

    evidence = f"{title} {item.get('aliases', [])}"
    scored: list[tuple[int, int, str, list[str]]] = []
    for priority, entry in enumerate(rules["categories"]):
        name = str(entry["name"])
        requires_any = entry.get("requires_any", [])
        requires_all = entry.get("requires_all", [])
        if requires_any and not any(keyword_matches(evidence, keyword) for keyword in requires_any):
            continue
        if requires_all and not all(keyword_matches(evidence, keyword) for keyword in requires_all):
            continue
        unique_keywords = {normalize(keyword).replace("_", " "): keyword for keyword in entry.get("keywords", [])}
        matches = [keyword for normalized, keyword in unique_keywords.items() if keyword_matches(evidence, normalized)]
        if matches:
            scored.append((len(matches), -priority, name, matches))
    if not scored:
        default = str(rules.get("default_category", "uncategorized"))
        if default not in category_names:
            raise WorkflowError("invalid_organization_rules", f"unknown default category: {default}")
        return default, []
    best = max(scored, key=lambda value: (value[0], value[1]))
    return best[2], best[3]


def effective_organization_title(root: Path, item: dict, pdf_path: Path, rules: dict) -> tuple[str, str]:
    rel_path = str(pdf_path.relative_to(root))
    for key in (rel_path, pdf_path.name, str(item.get("title", ""))):
        override = rule_override(rules, key)
        if override:
            return clean_organization_title(override), "override"

    title = clean_organization_title(str(item.get("title", "")))
    title_source = str(item.get("title_source", ""))
    if not title or title == pdf_path.stem or title_source == "filename":
        extracted = extract_pdf_title(pdf_path)
        if extracted:
            title = clean_organization_title(extracted)
            return title, "pdf"
    return title or pdf_path.stem, str(item.get("title_source", "index"))


def organization_items(root: Path, rules: dict) -> list[dict]:
    root = root.resolve()
    index = write_index(root)
    by_path: dict[str, tuple[str, dict]] = {}
    for item in index:
        path = item.get("path")
        if not path or not str(path).lower().endswith(".pdf"):
            continue
        rel_path = str(path)
        key = organization_key(rel_path)
        current = by_path.get(key)
        if current is None or str(item.get("source_type", "")) == "source_registry":
            by_path[key] = (rel_path, item)

    planned = []
    sources_by_path: dict[str, Path] = {}
    for rel_path, _ in by_path.values():
        lexical_path = root / rel_path
        if lexical_path.is_symlink():
            raise WorkflowError("unsafe_source_path", f"refusing to organize symlinked PDF: {rel_path}")
        resolved_path = workspace_path(root, lexical_path, "PDF source")
        if resolved_path.exists() and resolved_path.is_file():
            sources_by_path[rel_path] = resolved_path
    source_paths = set(sources_by_path.values())
    reserved: set[Path] = set()
    for _, (rel_path, item) in sorted(by_path.items()):
        source = sources_by_path.get(rel_path)
        if source is None:
            continue
        title, title_source = effective_organization_title(root, item, source, rules)
        category, evidence = classify_paper(item, title, rules, rel_path)
        target = workspace_path(root, Path("papers") / category / paper_filename(title, source.name), "organization target")
        collision = 1
        while target.resolve() in reserved or (target.exists() and target.resolve() not in {source} and target.resolve() not in source_paths):
            collision += 1
            target = workspace_path(root, target.with_name(f"{target.stem}_{collision}{target.suffix}"), "organization target")
        if target.resolve() in source_paths and target.resolve() != source:
            collision = 2
            candidate = workspace_path(root, target.with_name(f"{target.stem}_{collision}{target.suffix}"), "organization target")
            while candidate.resolve() in reserved or (candidate.exists() and candidate.resolve() not in source_paths):
                collision += 1
                candidate = workspace_path(root, target.with_name(f"{target.stem}_{collision}{target.suffix}"), "organization target")
            target = candidate
        reserved.add(target.resolve())
        planned.append(
            {
                "source": str(source.relative_to(root)),
                "target": str(target.relative_to(root)),
                "title": title,
                "title_source": title_source,
                "category": category,
                "evidence": evidence,
                "changed": source != target.resolve(),
            }
        )
    return planned


def rewrite_bib_sources(root: Path, mapping: dict[str, str]) -> None:
    path = workspace_path(root, "references/references.bib", "BibTeX path")
    if not path.exists():
        return
    by_name = {organization_key(Path(old).name): Path(new).name for old, new in mapping.items()}
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        match = re.match(r"(\s*%\s*Source:\s*)(.+?)(\s*)$", line.rstrip("\n"))
        if match:
            source = match.group(2).strip()
            replacement = mapping.get(source) or mapping.get(organization_key(source))
            if not replacement and organization_key(Path(source).name) in by_name:
                replacement = by_name[organization_key(Path(source).name)]
            if replacement:
                prefix = match.group(1)
                if "/" not in source:
                    replacement = Path(replacement).name
                line = f"{prefix}{replacement}{match.group(3)}\n"
        lines.append(line)
    path.write_text("".join(lines), encoding="utf-8")


def rewrite_source_registry(root: Path, mapping: dict[str, str]) -> None:
    records = load_source_records(root)
    if not records:
        return
    by_name = {organization_key(Path(old).name): new for old, new in mapping.items()}
    for record in records:
        for source in record.get("sources", []):
            if not isinstance(source, dict) or str(source.get("type", "")).lower() not in LOCAL_SOURCE_TYPES:
                continue
            locator = str(source.get("locator", ""))
            replacement = mapping.get(locator) or mapping.get(organization_key(locator)) or by_name.get(organization_key(Path(locator).name))
            if replacement:
                source["locator"] = replacement
                source["status"] = "available"
    write_source_records(root, records)


def mapped_locator(value: str, mapping: dict[str, str]) -> str | None:
    if value in mapping:
        return mapping[value]
    normalized = organization_key(value)
    for old, new in mapping.items():
        if organization_key(old) == normalized:
            return new
    return None


def remap_structured_paths(value: object, mapping: dict[str, str]) -> tuple[object, bool]:
    if isinstance(value, list):
        changed = False
        result = []
        for item in value:
            updated, item_changed = remap_structured_paths(item, mapping)
            result.append(updated)
            changed = changed or item_changed
        return result, changed
    if isinstance(value, dict):
        changed = False
        result = dict(value)
        for key, item in value.items():
            if key in {"path", "locator"} and isinstance(item, str):
                replacement = mapped_locator(item, mapping)
                if replacement is not None:
                    result[key] = replacement
                    changed = True
            else:
                updated, item_changed = remap_structured_paths(item, mapping)
                result[key] = updated
                changed = changed or item_changed
        return result, changed
    return value, False


def remap_note_link(root: Path, note_path: Path, value: str, mapping: dict[str, str]) -> str:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not parsed.path or Path(parsed.path).is_absolute():
        return value
    linked_path = (note_path.parent / parsed.path).resolve()
    for old, new in mapping.items():
        try:
            old_path = workspace_path(root, old, "previous PDF path")
        except WorkflowError:
            continue
        if linked_path != old_path:
            continue
        new_path = workspace_path(root, new, "organized PDF path")
        relative = os.path.relpath(new_path, start=note_path.parent.resolve()).replace(os.sep, "/")
        return urlunparse(("", "", relative, "", parsed.query, parsed.fragment))
    return value


def rewrite_note_links(root: Path, mapping: dict[str, str]) -> None:
    notes_dir = workspace_path(root, "notes", "notes directory")
    if not notes_dir.exists():
        return
    attribute = re.compile(r"(?P<prefix>\b(?:href|src)\s*=\s*(?P<quote>[\"']))(?P<value>[^\"']*)(?P=quote)", re.IGNORECASE)
    for path in notes_dir.rglob("*.html"):
        if path.is_symlink() or not is_workspace_path(root, path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        def replace(match: re.Match[str]) -> str:
            value = match.group("value")
            remapped = remap_note_link(root, path, value, mapping)
            return f"{match.group('prefix')}{remapped}{match.group('quote')}"

        updated = attribute.sub(replace, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def rewrite_workspace_references(root: Path, mapping: dict[str, str]) -> None:
    if not mapping:
        return
    # Only generated survey metadata and actual HTML link attributes are mutable.
    # Free-form notes and registered source documents are never text-rewritten.
    for manifest_path in survey_manifest_paths(root):
        if manifest_path.is_symlink() or not is_workspace_path(root, manifest_path):
            continue
        manifest = load_survey_manifest(manifest_path)
        updated, changed = remap_structured_paths(manifest, mapping)
        if not changed:
            continue
        manifest_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pack_path = workspace_path(root, manifest_path.parent / SURVEY_READING_PACK, "survey reading pack")
        pack_path.write_text(render_survey_reading_pack(root, manifest_path, updated), encoding="utf-8")
    rewrite_note_links(root, mapping)


def organization_journal_path(root: Path) -> Path:
    return workspace_path(root, ORGANIZATION_JOURNAL, "organization recovery journal")


def write_organization_journal(root: Path, mapping: dict[str, str], items: list[dict[str, str]]) -> Path:
    path = organization_journal_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "kind": "organization_recovery",
        "mapping": mapping,
        "items": items,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def load_organization_journal(root: Path) -> dict | None:
    path = organization_journal_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("invalid_organization_recovery", f"could not read organization recovery journal: {path}", str(exc)) from exc
    mapping = payload.get("mapping") if isinstance(payload, dict) else None
    items = payload.get("items") if isinstance(payload, dict) else None
    if payload.get("kind") != "organization_recovery" or not isinstance(mapping, dict) or not all(
        isinstance(old, str) and isinstance(new, str) for old, new in mapping.items()
    ) or not isinstance(items, list) or not all(
        isinstance(item, dict) and all(isinstance(item.get(key), str) for key in ("source", "target", "temporary"))
        for item in items
    ):
        raise WorkflowError("invalid_organization_recovery", f"invalid organization recovery journal: {path}")
    return payload


def apply_organization_metadata(root: Path, reference_mapping: dict[str, str]) -> int:
    mapping = {organization_key(old): new for old, new in reference_mapping.items()}
    rewrite_bib_sources(root, mapping)
    rewrite_source_registry(root, mapping)
    rewrite_workspace_references(root, reference_mapping)
    return len(write_index(root))


def recover_pending_organization(root: Path) -> dict | None:
    root = root.resolve()
    payload = load_organization_journal(root)
    if payload is None:
        return None
    completed_mapping: dict[str, str] = {}
    restored = 0
    temporary_paths: list[Path] = []
    for item in payload["items"]:
        source = workspace_path(root, item["source"], "organization recovery source")
        target = workspace_path(root, item["target"], "organization recovery target")
        temporary = workspace_path(root, item["temporary"], "organization recovery temporary file")
        temporary_paths.append(temporary)
        source_exists = source.exists()
        target_exists = target.exists()
        temporary_exists = temporary.exists()
        if not source_exists and target_exists:
            completed_mapping[item["source"]] = item["target"]
            if temporary_exists:
                temporary.unlink()
            continue
        if not source_exists and not target_exists and temporary_exists:
            restore_staged_file(root, temporary, source)
            restored += 1
            continue
        if source_exists and not target_exists and not temporary_exists:
            continue
        raise WorkflowError(
            "organization_recovery_conflict",
            "organization recovery found an ambiguous source/target/temporary state",
            {"source": item["source"], "target": item["target"], "temporary": item["temporary"]},
        )
    index_entries = apply_organization_metadata(root, completed_mapping) if completed_mapping else len(write_index(root))
    organization_journal_path(root).unlink()
    staging_dirs = {path.parent for path in temporary_paths}
    for staging in staging_dirs:
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()
    return {"recovered": len(completed_mapping), "restored": restored, "index_entries": index_entries}


@contextmanager
def secure_workspace_parent(root: Path, target: Path, label: str):
    """Open a writable target parent through no-follow directory descriptors."""
    root = root.resolve()
    resolved_target = workspace_path(root, target, label)
    relative = resolved_target.relative_to(root)
    if len(relative.parts) < 1:
        raise WorkflowError("workspace_path_escape", f"{label} must name a file inside the workspace")
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, flag) for flag in required_flags):
        raise WorkflowError("secure_path_operation_unavailable", "secure local file operations require O_DIRECTORY and O_NOFOLLOW")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, directory_flags)
    try:
        for component in relative.parts[:-1]:
            try:
                child = os.open(component, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(component, dir_fd=descriptor)
                child = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, relative.name
    finally:
        os.close(descriptor)


def file_identity(root: Path, path: Path) -> tuple[int, int]:
    with secure_workspace_parent(root, path, "managed file") as (parent_fd, name):
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise WorkflowError("unsafe_target_path", f"managed target is not a regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def has_file_identity(root: Path, path: Path, identity: tuple[int, int]) -> bool:
    try:
        return file_identity(root, path) == identity
    except (OSError, WorkflowError):
        return False


def unlink_workspace_file(root: Path, path: Path, identity: tuple[int, int] | None = None) -> None:
    with secure_workspace_parent(root, path, "managed file") as (parent_fd, name):
        if identity is not None:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != identity:
                return
        os.unlink(name, dir_fd=parent_fd)


def place_file_without_overwrite(root: Path, source: Path, target: Path) -> tuple[int, int]:
    """Create a target from a staged regular file without replacing another writer's file."""
    with secure_workspace_parent(root, target, "organization target") as (parent_fd, name):
        try:
            os.link(source, name, dst_dir_fd=parent_fd, follow_symlinks=False)
        except FileExistsError as exc:
            raise WorkflowError("target_conflict", f"organization target already exists: {target}") from exc
        except OSError as exc:
            unsupported = {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP}
            if exc.errno not in unsupported:
                raise WorkflowError("organization_move_failed", f"could not stage organization target: {target}", str(exc)) from exc
            copied_identity: tuple[int, int] | None = None
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                copied_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
                with source.open("rb") as original, os.fdopen(copied_fd, "wb") as copied:
                    metadata = os.fstat(copied.fileno())
                    copied_identity = metadata.st_dev, metadata.st_ino
                    shutil.copyfileobj(original, copied)
                    copied.flush()
                    os.fsync(copied.fileno())
            except FileExistsError as copy_exc:
                raise WorkflowError("target_conflict", f"organization target already exists: {target}") from copy_exc
            except OSError as copy_exc:
                if copied_identity is not None:
                    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if stat.S_ISREG(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == copied_identity:
                        os.unlink(name, dir_fd=parent_fd)
                raise WorkflowError("organization_move_failed", f"could not stage organization target: {target}", str(copy_exc)) from copy_exc
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise WorkflowError("unsafe_target_path", f"organization target is not a regular file: {target}")
        return metadata.st_dev, metadata.st_ino


def move_file_without_overwrite(root: Path, source: Path, target: Path) -> tuple[int, int]:
    """Move a staged regular file while preserving a concurrently created target."""
    identity = place_file_without_overwrite(root, source, target)
    try:
        source.unlink()
    except OSError as exc:
        if has_file_identity(root, target, identity):
            unlink_workspace_file(root, target, identity)
        raise WorkflowError("organization_move_failed", f"could not remove staged file: {source}", str(exc)) from exc
    return identity


def restore_staged_file(root: Path, temporary: Path, source: Path) -> None:
    if not temporary.exists():
        return
    try:
        move_file_without_overwrite(root, temporary, source)
        return
    except WorkflowError as exc:
        if exc.code != "target_conflict":
            raise
    for suffix in range(1, 1000):
        recovered = source.with_name(f"{source.stem}_recovered_{suffix}{source.suffix}")
        try:
            move_file_without_overwrite(root, temporary, recovered)
            return
        except WorkflowError as exc:
            if exc.code != "target_conflict":
                raise
    raise WorkflowError("organization_rollback_incomplete", f"could not restore staged PDF: {temporary}")


def apply_organization(root: Path, planned: list[dict]) -> dict:
    root = root.resolve()
    active = [item for item in planned if item["changed"]]
    mapping = {organization_key(item["source"]): item["target"] for item in active}
    reference_mapping = {item["source"]: item["target"] for item in active}
    if not active:
        return {"moved": 0, "mapping": {}, "plan": planned}

    actions: list[tuple[Path, Path]] = []
    for item in active:
        source_lexical = root / item["source"]
        if source_lexical.is_symlink():
            raise WorkflowError("unsafe_source_path", f"refusing to organize symlinked PDF: {item['source']}")
        source = workspace_path(root, source_lexical, "PDF source")
        target = workspace_path(root, root / item["target"], "organization target")
        if not source.exists() or not source.is_file():
            raise WorkflowError("source_missing", f"planned PDF no longer exists: {item['source']}")
        actions.append((source, target))

    staging = workspace_path(root, Path(tempfile.mkdtemp(prefix=".literature-workflow-", dir=root)), "staging directory")
    planned_staged = [(staging / f"{idx:04d}.pdf", source, target) for idx, (source, target) in enumerate(actions)]
    journal = write_organization_journal(
        root,
        reference_mapping,
        [
            {
                "source": str(source.relative_to(root)),
                "target": str(target.relative_to(root)),
                "temporary": str(temporary.relative_to(root)),
            }
            for temporary, source, target in planned_staged
        ],
    )
    staged: list[tuple[Path, Path, Path]] = []
    finalized: dict[Path, tuple[int, int]] = {}
    try:
        for temporary, source, target in planned_staged:
            shutil.move(str(source), str(temporary))
            staged.append((temporary, source, target))
        for temporary, source, target in staged:
            finalized[target] = place_file_without_overwrite(root, temporary, target)
    except Exception as original_error:
        rollback_incomplete = False
        for temporary, source, target in reversed(staged):
            try:
                identity = finalized.get(target)
                if identity is not None:
                    unlink_workspace_file(root, target, identity)
                restore_staged_file(root, temporary, source)
            except (OSError, WorkflowError):
                rollback_incomplete = True
        if rollback_incomplete or any(temporary.exists() for temporary, _, _ in staged):
            raise WorkflowError(
                "organization_rollback_incomplete",
                f"organization rollback kept staged PDFs at: {staging}",
                {"original_error": str(original_error), "staging": str(staging)},
            ) from original_error
        journal.unlink()
        raise

    try:
        index_entries = apply_organization_metadata(root, reference_mapping)
    except Exception as exc:
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
        raise WorkflowError(
            "organization_metadata_pending",
            "PDFs were moved, but metadata updates are pending recovery",
            {"journal": str(journal.relative_to(root)), "error": str(exc)},
        ) from exc
    else:
        journal.unlink()
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
        return {"moved": len(active), "mapping": mapping, "plan": planned, "index_entries": index_entries}
    finally:
        if not any(temporary.exists() for temporary, _, _ in staged):
            shutil.rmtree(staging, ignore_errors=True)


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def resolve_add_source(source: str) -> tuple[str, str | None]:
    source = source.strip()
    if not source:
        raise WorkflowError("empty_source", "PDF source is empty")
    exact_arxiv = ARXIV_ID_RE.match(source)
    if exact_arxiv:
        arxiv_id = exact_arxiv.group(0)
        return arxiv_pdf_url(arxiv_id), f"{arxiv_id}.pdf"

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        match = ARXIV_IN_TEXT_RE.search(source)
        if parsed.netloc.endswith("arxiv.org") and match:
            arxiv_id = match.group(0)
            return arxiv_pdf_url(arxiv_id), f"{arxiv_id}.pdf"
        return source, normalize_pdf_name(Path(parsed.path).name)

    return str(Path(os.path.expanduser(source)).resolve()), None


def is_public_download_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_unspecified,
            ip.is_reserved,
            getattr(ip, "is_site_local", False),
        )
    ):
        return False
    if ip.version == 6 and any(ip in network for network in WELL_KNOWN_NAT64_PREFIXES):
        return False
    return ip.is_global


def validate_download_url(url: str) -> tuple[str, ...]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WorkflowError("unsafe_download_url", "download URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise WorkflowError("unsafe_download_url", "download URL must not contain credentials")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise WorkflowError("download_host_unavailable", f"could not resolve download host: {parsed.hostname}") from exc
    resolved = tuple(dict.fromkeys(entry[4][0] for entry in addresses))
    if not resolved:
        raise WorkflowError("download_host_unavailable", f"could not resolve download host: {parsed.hostname}")
    for address in resolved:
        try:
            if not is_public_download_address(address):
                raise WorkflowError("unsafe_download_url", "download host must resolve only to public IP addresses")
        except ValueError as exc:
            raise WorkflowError("download_host_unavailable", f"download host returned an invalid address: {address}") from exc
    return resolved


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise WorkflowError("download_redirect_blocked", "download URL redirected; use its final public PDF URL instead")


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, *, address: str, **kwargs: object) -> None:
        self._pinned_address = address
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_address, self.port), self.timeout, self.source_address)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, address: str, **kwargs: object) -> None:
        self._pinned_address = address
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_address, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            server_hostname = self._tunnel_host
        else:
            server_hostname = self.host
        self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)


class PinnedHTTPHandler(HTTPHandler):
    def __init__(self, address: str) -> None:
        super().__init__()
        self._pinned_address = address

    def http_open(self, request: Request):  # type: ignore[no-untyped-def]
        return self.do_open(
            lambda host, **kwargs: PinnedHTTPConnection(host, address=self._pinned_address, **kwargs),
            request,
        )


class PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, address: str) -> None:
        super().__init__()
        self._pinned_address = address

    def https_open(self, request: Request):  # type: ignore[no-untyped-def]
        return self.do_open(
            lambda host, **kwargs: PinnedHTTPSConnection(host, address=self._pinned_address, **kwargs),
            request,
            context=self._context,
        )


def download(root: Path, url: str, target: Path) -> None:
    addresses = validate_download_url(url)
    request = Request(url, headers={"User-Agent": "literature-workflow-skill/1.0"})
    # Disable environment proxies and connect only to the DNS result just vetted above.
    opener = build_opener(
        ProxyHandler({}),
        RejectRedirects(),
        PinnedHTTPHandler(addresses[0]),
        PinnedHTTPSHandler(addresses[0]),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".literature-download-", suffix=".pdf", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as destination, opener.open(request, timeout=60) as response:
            content_length = response.headers.get("Content-Length")
            try:
                declared_size = int(content_length) if content_length else None
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > MAX_DOWNLOAD_BYTES:
                raise WorkflowError("download_too_large", f"PDF exceeds {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MiB limit")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise WorkflowError("download_too_large", f"PDF exceeds {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MiB limit")
                destination.write(chunk)
        if not is_pdf(temporary):
            raise WorkflowError("download_not_pdf", "downloaded content is not a valid PDF")
        move_file_without_overwrite(root, temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def copy_file_without_overwrite(root: Path, source: Path, target: Path) -> None:
    with secure_workspace_parent(root, target, "import target") as (parent_fd, name):
        copied_identity: tuple[int, int] | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            copied_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
            with source.open("rb") as original, os.fdopen(copied_fd, "wb") as copied:
                metadata = os.fstat(copied.fileno())
                copied_identity = metadata.st_dev, metadata.st_ino
                shutil.copyfileobj(original, copied)
                copied.flush()
                os.fsync(copied.fileno())
        except FileExistsError as exc:
            raise WorkflowError("target_conflict", f"import target already exists: {target}") from exc
        except OSError as exc:
            if copied_identity is not None:
                metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISREG(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == copied_identity:
                    os.unlink(name, dir_fd=parent_fd)
            raise WorkflowError("local_import_failed", f"could not copy PDF into workspace: {target}", str(exc)) from exc


def add_pdf(root: Path, source: str, name: str | None = None) -> Path:
    root = root.resolve()
    ensure_root(root)
    resolved, inferred_name = resolve_add_source(source)
    parsed = urlparse(resolved)

    if parsed.scheme not in {"http", "https"}:
        src = Path(resolved)
        if not src.exists():
            raise WorkflowError("source_missing", f"source not found: {src}")
        if not src.is_file():
            raise WorkflowError("source_not_file", f"source is not a file: {src}")
        if not is_pdf(src):
            raise WorkflowError("source_not_pdf", f"source is not a PDF: {src}")
        try:
            src.relative_to(root)
            return src.resolve()
        except ValueError:
            pass

    filename = normalize_pdf_name(name or inferred_name or Path(resolved).name)
    target = unique_path(workspace_path(root, filename, "download destination"))

    if parsed.scheme in {"http", "https"}:
        try:
            download(root, resolved, target)
        except WorkflowError:
            raise
        except Exception as exc:
            raise WorkflowError("download_failed", f"failed to download PDF: {resolved}", str(exc)) from exc
    else:
        import shutil

        try:
            copy_file_without_overwrite(root, Path(resolved), target)
        except WorkflowError:
            raise

    if not is_pdf(target):
        target.unlink(missing_ok=True)
        raise WorkflowError("download_not_pdf", f"added file is not a valid PDF: {target}")
    return target


def source_registry_path(root: Path) -> Path:
    return workspace_path(root, SOURCE_REGISTRY, "source registry")


def load_source_records(root: Path) -> list[dict]:
    path = source_registry_path(root)
    if not path.exists():
        return []
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkflowError("invalid_source_registry", f"invalid JSON in {path}:{line_no}", str(exc)) from exc
        record.setdefault("id", entity_id(str(record.get("title", "untitled"))))
        record.setdefault("kind", "paper")
        record.setdefault("aliases", [])
        record.setdefault("sources", [])
        records.append(record)
    return records


def write_source_records(root: Path, records: list[dict]) -> None:
    path = source_registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )


def setup_workspace(root: Path) -> dict:
    created: list[str] = []
    preserved: list[str] = []
    if root.exists():
        ensure_root(root)
    else:
        root.mkdir(parents=True, exist_ok=True)
        created.append(".")
    root = root.resolve()
    for dirname in WORKSPACE_DIRS:
        path = workspace_path(root, dirname, "workspace directory")
        if path.exists():
            preserved.append(dirname)
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(dirname)

    source_path = source_registry_path(root)
    if source_path.exists():
        preserved.append(str(SOURCE_REGISTRY))
    else:
        source_path.write_text("", encoding="utf-8")
        created.append(str(SOURCE_REGISTRY))

    rules_path = workspace_path(root, ORGANIZATION_RULES, "organization rules")
    if rules_path.exists():
        preserved.append(str(ORGANIZATION_RULES))
    else:
        rules_path.write_text(json.dumps(DEFAULT_ORGANIZATION_RULES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(ORGANIZATION_RULES))

    index = write_index(root)
    return {
        "root": str(root),
        "created": created,
        "preserved": preserved,
        "index_entries": len(index),
        "agents_md": "create or update conversationally from user preferences; do not hard-code it in setup",
    }


def infer_source_type(locator: str) -> str:
    value = locator.strip()
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if "github.com" in parsed.netloc:
            return "repo"
        if parsed.netloc.endswith("arxiv.org") or ARXIV_IN_TEXT_RE.search(value):
            return "arxiv"
        return "url"
    if ARXIV_ID_RE.match(value):
        return "arxiv"
    suffix = Path(value).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".md", ".txt", ".rst"}:
        return "text"
    return "path"


def normalize_source_locator(root: Path, locator: str, source_type: str) -> str:
    locator = locator.strip()
    if source_type in {"arxiv"}:
        match = ARXIV_IN_TEXT_RE.search(locator)
        return match.group(0) if match else locator.replace("arXiv:", "").strip()
    if source_type not in LOCAL_SOURCE_TYPES:
        return locator
    path = Path(os.path.expanduser(locator))
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


def local_source_path(root: Path, locator: str, source_type: str) -> Path | None:
    if source_type not in LOCAL_SOURCE_TYPES:
        return None
    path = Path(os.path.expanduser(locator))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def make_source(root: Path, locator: str, source_type: str | None = None, role: str = "supplement") -> dict:
    resolved_type = source_type or infer_source_type(locator)
    normalized = normalize_source_locator(root, locator, resolved_type)
    path = local_source_path(root, normalized, resolved_type)
    if resolved_type == "pdf" and path and path.exists() and not is_pdf(path):
        raise WorkflowError("source_not_pdf", f"source is not a PDF: {path}")
    status = "available" if path and path.exists() else ("missing" if path else "external")
    return {
        "type": resolved_type,
        "locator": normalized,
        "role": role,
        "status": status,
    }


def parse_typed_source(value: str) -> tuple[str | None, str]:
    if "=" not in value:
        return None, value
    source_type, locator = value.split("=", 1)
    source_type = source_type.strip().lower()
    if not source_type or not locator.strip():
        raise WorkflowError("invalid_source", "generic --source must be LOCATOR or type=LOCATOR")
    return source_type, locator.strip()


def collect_sources(args: argparse.Namespace) -> list[dict]:
    pairs: list[tuple[str | None, str]] = []
    for source_type in ("pdf", "url", "arxiv", "doi", "repo", "doc"):
        for locator in getattr(args, source_type, []) or []:
            pairs.append((source_type, locator))
    for value in getattr(args, "source", []) or []:
        pairs.append(parse_typed_source(value))

    sources = []
    for idx, (source_type, locator) in enumerate(pairs):
        role = "primary" if idx == 0 else "supplement"
        sources.append(make_source(args.root, locator, source_type, role))
    return sources


def source_key(source: dict) -> str:
    return f"{str(source.get('type', '')).lower()}:{str(source.get('locator', '')).strip().lower()}"


def merge_source_lists(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for source in [*existing, *incoming]:
        key = source_key(source)
        if key in seen:
            continue
        merged.append(source)
        seen.add(key)
    return merged


def record_aliases(record: dict) -> list[str]:
    aliases = [str(record.get("title", "")), str(record.get("id", ""))]
    aliases.extend(str(alias) for alias in record.get("aliases", []) if alias)
    for source in record.get("sources", []):
        locator = str(source.get("locator", ""))
        if locator:
            aliases.extend([locator, Path(locator).name, Path(locator).stem])
            if source.get("type") == "arxiv":
                aliases.append(f"arXiv:{locator}")
    return sorted({alias for alias in aliases if alias})


def registry_score_item(record: dict) -> dict:
    aliases = record_aliases(record)
    return {
        "title": record.get("title", ""),
        "aliases": aliases,
        "normalized_aliases": [re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip() for alias in aliases],
    }


def find_source_record(records: list[dict], query: str) -> tuple[int, dict] | tuple[None, None]:
    matches = sorted(
        ((score(query, registry_score_item(record)), idx, record) for idx, record in enumerate(records)),
        key=lambda item: item[0],
        reverse=True,
    )
    if not matches or matches[0][0] < 0.92:
        return None, None
    return matches[0][1], matches[0][2]


def record_from_index_item(item: dict) -> dict:
    return {
        "id": str(item.get("entity_id") or entity_id(str(item.get("title", "untitled")))),
        "kind": str(item.get("kind", "paper")),
        "title": str(item.get("title", "untitled")),
        "aliases": sorted(str(alias) for alias in item.get("aliases", []) if alias),
        "sources": item.get("sources") or (
            [{"type": "pdf", "locator": item["path"], "role": "primary", "status": "available"}]
            if item.get("path")
            else []
        ),
    }


def relative_locator(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


def source_record_for_source(records: list[dict], source: dict) -> dict | None:
    key = source_key(source)
    for record in records:
        for candidate in record.get("sources", []):
            if isinstance(candidate, dict) and source_key(candidate) == key:
                return record
    return None


def unique_record_id(records: list[dict], title: str) -> str:
    base = entity_id(title) or "source"
    existing = {str(record.get("id", "")) for record in records}
    if base not in existing:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base}_{suffix}"
        if candidate not in existing:
            return candidate
    raise WorkflowError("entity_id_collision", f"too many source entities named like: {base}")


def resolve_local_document(root: Path, value: str) -> Path:
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.exists():
        raise WorkflowError("source_missing", f"source document does not exist: {value}")
    if not path.is_file():
        raise WorkflowError("source_not_file", f"source document is not a file: {value}")
    if path.suffix.lower() not in SURVEY_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SURVEY_DOCUMENT_SUFFIXES))
        raise WorkflowError("unsupported_survey_source", f"survey sources must be one of: {supported}")
    return path


def inferred_document_title(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt", ".rst", ".html", ".htm"}:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:16384]
        except OSError:
            text = ""
        heading = re.search(r"(?m)^\s{0,3}#\s+(.+?)\s*$", text)
        if heading:
            return clean_text(heading.group(1))
        html_title = re.search(r"(?is)<title[^>]*>\s*(.*?)\s*</title>", text)
        if html_title:
            return clean_text(re.sub(r"<[^>]+>", " ", html_title.group(1)))
    fallback = re.sub(r"[_-]+", " ", path.stem).strip()
    return fallback.title() or "Untitled Survey Source"


def ensure_survey_document_entity(root: Path, path: Path, title: str | None = None) -> tuple[dict, dict]:
    source_type = infer_source_type(str(path))
    if source_type == "pdf":
        raise WorkflowError("invalid_survey_source", "use --paper for PDFs; survey source documents must be non-PDF files")
    source = make_source(root, str(path), source_type, role="reference")
    if source["status"] != "available":
        raise WorkflowError("source_missing", f"survey source is unavailable: {path}")

    records = load_source_records(root)
    existing = source_record_for_source(records, source)
    if existing is not None:
        return existing, source

    record_title = (title or inferred_document_title(path)).strip()
    if not record_title:
        raise WorkflowError("empty_source_title", f"could not determine a title for source: {path}")
    record = {
        "id": unique_record_id(records, record_title),
        "kind": "survey",
        "title": record_title,
        "aliases": [],
        "sources": [source],
    }
    records.append(record)
    write_source_records(root, records)
    return record, source


def move_survey_source_document(root: Path, path: Path) -> Path:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkflowError("source_outside_workspace", "only source documents inside the workspace can be managed by moving") from exc
    managed_sources = workspace_path(root, SURVEY_SOURCES_DIR, "survey source directory")
    if path.is_relative_to(managed_sources):
        return path
    target_dir = managed_sources
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(workspace_path(root, target_dir / path.name, "survey source destination"))
    old_source = make_source(root, str(path), infer_source_type(str(path)), role="reference")
    try:
        shutil.move(str(path), str(target))
    except OSError as exc:
        raise WorkflowError("source_move_failed", f"failed to move source document: {path}", str(exc)) from exc
    new_source = make_source(root, str(target), infer_source_type(str(target)), role="reference")
    mapping = {str(old_source["locator"]): str(new_source["locator"])}
    rewrite_source_registry(root, mapping)
    rewrite_workspace_references(root, mapping)
    return target


def survey_slug(title: str) -> str:
    slug = normalize(title)[:96].strip("_")
    if not slug:
        raise WorkflowError("invalid_survey_title", "survey title must contain letters or numbers")
    return slug


def survey_manifest_paths(root: Path) -> list[Path]:
    directory = workspace_path(root, SURVEYS_DIR, "surveys directory")
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob(f"*/{SURVEY_MANIFEST}") if path.is_file())


def load_survey_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("invalid_survey_manifest", f"could not read survey manifest: {path}", str(exc)) from exc
    if not isinstance(payload, dict) or payload.get("kind") != "literature_survey":
        raise WorkflowError("invalid_survey_manifest", f"not a literature survey manifest: {path}")
    if not isinstance(payload.get("papers"), list) or not isinstance(payload.get("source_documents"), list):
        raise WorkflowError("invalid_survey_manifest", f"survey manifest has invalid paper/source lists: {path}")
    return payload


def resolve_survey_manifest(root: Path, query: str) -> Path:
    if not query.strip():
        raise WorkflowError("empty_survey_query", "survey query is empty")
    candidate_name = Path(query).name
    if candidate_name != query or candidate_name in {".", ".."}:
        raise WorkflowError("invalid_survey_query", "survey query must be a title or one survey directory name")
    direct = workspace_path(root, SURVEYS_DIR / candidate_name / SURVEY_MANIFEST, "survey manifest")
    if direct.exists():
        return direct

    normalized = normalize(query)
    matches = []
    for path in survey_manifest_paths(root):
        payload = load_survey_manifest(path)
        candidates = {normalize(path.parent.name), normalize(str(payload.get("slug", ""))), normalize(str(payload.get("title", "")))}
        if normalized in candidates:
            matches.append(path)
    if not matches:
        raise WorkflowError("survey_not_found", f"no survey found: {query}")
    if len(matches) > 1:
        raise WorkflowError("ambiguous_survey", f"survey query is ambiguous: {query}", [str(path.relative_to(root)) for path in matches])
    return matches[0]


def survey_paper_entry(root: Path, query: str) -> dict:
    pdf_path, item = resolve_pdf(root, query)
    if item is None:
        for candidate in read_index(root):
            candidate_path = candidate.get("path")
            if candidate_path and (root / str(candidate_path)).resolve() == pdf_path:
                item = candidate
                break
    title = str(item.get("title")) if item and item.get("title") else pdf_path.stem
    sources = item.get("sources", []) if item else []
    return {
        "entity_id": str(item.get("entity_id") if item else entity_id(title)),
        "title": title,
        "path": relative_locator(root, pdf_path),
        "sources": sources,
        "status": "available" if pdf_path.exists() else "missing",
    }


def survey_document_entry(record: dict, source: dict) -> dict:
    return {
        "entity_id": str(record.get("id", "")),
        "title": str(record.get("title", "Untitled Survey Source")),
        "source": source,
    }


def unique_survey_papers(entries: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen = set()
    for entry in entries:
        key = str(entry.get("entity_id") or entry.get("path"))
        if key in seen:
            continue
        unique.append(entry)
        seen.add(key)
    return unique


def local_link_from(path: Path, root: Path, locator: str, source_type: str) -> str:
    local_path = local_source_path(root, locator, source_type)
    if local_path is None:
        return locator
    try:
        return os.path.relpath(local_path, start=path.parent)
    except ValueError:
        return str(local_path)


def markdown_label(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def render_survey_reading_pack(root: Path, manifest_path: Path, manifest: dict) -> str:
    lines = [f"# {manifest['title']}", "", f"Scope: {manifest['scope']}", "", "## Selected Papers", ""]
    for paper in manifest["papers"]:
        title = markdown_label(str(paper.get("title", "Untitled Paper")))
        link = local_link_from(manifest_path, root, str(paper.get("path", "")), "pdf")
        lines.append(f"- [{title}]({link})")
    if manifest["source_documents"]:
        lines.extend(["", "## Read-only Source Documents", ""])
        for document in manifest["source_documents"]:
            source = document.get("source", {})
            source_type = str(source.get("type", "path"))
            locator = str(source.get("locator", ""))
            title = markdown_label(str(document.get("title", "Untitled Source")))
            link = local_link_from(manifest_path, root, locator, source_type)
            lines.append(f"- [{title}]({link})")
    lines.extend(
        [
            "",
            "This generated pack defines scope and sources. It is not survey prose; source documents remain read-only unless the user explicitly requests a rewrite.",
            "",
        ]
    )
    return "\n".join(lines)


def write_survey_manifest(root: Path, directory: Path, manifest: dict) -> dict:
    directory = workspace_path(root, directory, "survey directory")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace_path(root, directory / SURVEY_MANIFEST, "survey manifest")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pack_path = workspace_path(root, directory / SURVEY_READING_PACK, "survey reading pack")
    pack_path.write_text(render_survey_reading_pack(root, manifest_path, manifest), encoding="utf-8")
    return {
        "manifest": str(manifest_path.relative_to(root)),
        "reading_pack": str(pack_path.relative_to(root)),
        "papers": len(manifest["papers"]),
        "source_documents": len(manifest["source_documents"]),
    }


def refresh_survey_paper(root: Path, previous: dict) -> dict:
    queries = [str(previous.get("title", "")), str(previous.get("entity_id", "")), str(previous.get("path", ""))]
    for query in queries:
        if not query:
            continue
        try:
            return survey_paper_entry(root, query)
        except WorkflowError:
            continue
    refreshed = dict(previous)
    refreshed["status"] = "missing"
    return refreshed


def refresh_survey_document(root: Path, previous: dict, records: list[dict]) -> dict:
    record = next((item for item in records if str(item.get("id", "")) == str(previous.get("entity_id", ""))), None)
    source = dict(previous.get("source", {}))
    if record is not None:
        for candidate in record.get("sources", []):
            if isinstance(candidate, dict) and str(candidate.get("type", "")).lower() in LOCAL_SOURCE_TYPES and candidate.get("type") != "pdf":
                source = dict(candidate)
                break
    source_type = str(source.get("type", "path"))
    locator = str(source.get("locator", ""))
    path = local_source_path(root, locator, source_type)
    if path is not None:
        source["status"] = "available" if path.exists() else "missing"
    return {
        "entity_id": str(record.get("id")) if record is not None else str(previous.get("entity_id", "")),
        "title": str(record.get("title")) if record is not None else str(previous.get("title", "Untitled Survey Source")),
        "source": source,
    }


def create_or_update_survey(root: Path, title: str, scope: str, papers: list[str], sources: list[str], update: bool) -> dict:
    slug = survey_slug(title)
    directory = workspace_path(root, SURVEYS_DIR / slug, "survey directory")
    manifest_path = workspace_path(root, directory / SURVEY_MANIFEST, "survey manifest")
    existing = load_survey_manifest(manifest_path) if manifest_path.exists() else None
    if existing is None and directory.exists():
        raise WorkflowError("survey_path_conflict", f"survey directory already exists without a manifest: {directory.relative_to(root)}")
    if existing is not None and not update:
        raise WorkflowError("survey_exists", f"survey already exists: {directory.relative_to(root)}; use --update to replace its scope list")
    if not papers:
        raise WorkflowError("empty_survey_papers", "a survey scope needs at least one --paper")

    paper_entries = unique_survey_papers([survey_paper_entry(root, query) for query in papers])
    document_entries = []
    for source_path in sources:
        path = resolve_local_document(root, source_path)
        record, source = ensure_survey_document_entity(root, path)
        document_entries.append(survey_document_entry(record, source))

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "version": 1,
        "kind": "literature_survey",
        "slug": slug,
        "title": title.strip(),
        "scope": scope.strip(),
        "papers": paper_entries,
        "source_documents": document_entries,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    payload = write_survey_manifest(root, directory, manifest)
    payload["index_entries"] = len(write_index(root))
    return payload


def refresh_survey(root: Path, query: str) -> dict:
    manifest_path = resolve_survey_manifest(root, query)
    manifest = load_survey_manifest(manifest_path)
    records = load_source_records(root)
    manifest["papers"] = [refresh_survey_paper(root, item) for item in manifest["papers"]]
    manifest["source_documents"] = [refresh_survey_document(root, item, records) for item in manifest["source_documents"]]
    manifest["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = write_survey_manifest(root, manifest_path.parent, manifest)
    payload["missing_papers"] = sum(1 for item in manifest["papers"] if item.get("status") != "available")
    payload["missing_source_documents"] = sum(
        1 for item in manifest["source_documents"] if item.get("source", {}).get("status") == "missing"
    )
    return payload


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_extractor_status() -> dict[str, bool]:
    try:
        import pypdf  # noqa: F401

        pypdf = True
    except ImportError:
        pypdf = False
    try:
        import fitz  # noqa: F401

        pymupdf = True
    except ImportError:
        pymupdf = False
    return {
        "pypdf": pypdf,
        "pymupdf": pymupdf,
        "pdftotext": shutil.which("pdftotext") is not None,
    }


def extract_pdf_pages_with_pypdf(pdf_path: Path, max_pages: int | None) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise WorkflowError("text_extractor_missing", "Python package `pypdf` is not available") from exc

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise WorkflowError("pdf_read_failed", f"failed to read PDF: {pdf_path}", str(exc)) from exc
    pages = []
    selected = reader.pages if max_pages is None else reader.pages[:max_pages]
    for page in selected:
        pages.append(page.extract_text() or "")
    return pages


def extract_pdf_pages_with_pymupdf(pdf_path: Path, max_pages: int | None) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise WorkflowError("text_extractor_missing", "Python package `PyMuPDF` is not available") from exc

    try:
        doc = fitz.open(str(pdf_path))
        limit = len(doc) if max_pages is None else min(max_pages, len(doc))
        return [doc.load_page(idx).get_text() or "" for idx in range(limit)]
    except Exception as exc:
        raise WorkflowError("pdf_read_failed", f"failed to read PDF: {pdf_path}", str(exc)) from exc


def extract_pdf_pages_with_pdftotext(pdf_path: Path, max_pages: int | None) -> list[str]:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise WorkflowError("text_extractor_missing", "system command `pdftotext` is not available")
    command = [pdftotext]
    if max_pages is not None:
        command.extend(["-f", "1", "-l", str(max_pages)])
    command.extend([str(pdf_path), "-"])
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise WorkflowError(
            "pdf_read_failed",
            f"failed to read PDF with pdftotext: {pdf_path}",
            {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]},
        )
    pages = result.stdout.split("\f")
    return [page for page in pages if page.strip()]


def extract_pdf_pages(pdf_path: Path, max_pages: int | None = None) -> list[str]:
    status = text_extractor_status()
    if status["pypdf"]:
        return extract_pdf_pages_with_pypdf(pdf_path, max_pages)
    if status["pymupdf"]:
        return extract_pdf_pages_with_pymupdf(pdf_path, max_pages)
    if status["pdftotext"]:
        return extract_pdf_pages_with_pdftotext(pdf_path, max_pages)
    raise WorkflowError(
        "text_extractor_missing",
        "no PDF text extractor available; install pypdf, PyMuPDF, or poppler pdftotext",
        status,
    )


def extract_title_from_first_page(first_page: str, fallback: str) -> str:
    lines = [clean_text(line) for line in first_page.splitlines()]
    lines = [line for line in lines if line and not re.fullmatch(r"\d+", line)]
    if not lines:
        return fallback
    title = lines[0]
    for line in lines[1:4]:
        if "@" in line or re.search(r"\b(university|institute|college|school|department)\b", line, re.I):
            break
        candidate = f"{title} {line}"
        if len(candidate) > 220:
            break
        title = candidate
        if ":" in title and len(title) > 80:
            break
    return title


def between(text: str, start_pattern: str, end_pattern: str) -> str:
    start = re.search(start_pattern, text, flags=re.I | re.M)
    if not start:
        return ""
    end = re.search(end_pattern, text[start.end() :], flags=re.I | re.M)
    if not end:
        return clean_text(text[start.end() :])
    return clean_text(text[start.end() : start.end() + end.start()])


METHOD_LIKE_STARTS = (
    (
        "method",
        r"(^|\n)\s*(?:\d+(?:\.\d+)*\.?\s*)?(?:the\s+)?(?:proposed\s+)?(?:methodology|methods?|approach)\b[^\n]{0,120}",
    ),
    (
        "workflow",
        r"(^|\n)\s*(?:\d+(?:\.\d+)*\.?\s*)?[^\n]{0,80}\b(?:workflow|pipeline)\b[^\n]{0,120}",
    ),
    (
        "system",
        r"(^|\n)\s*(?:\d+(?:\.\d+)*\.?\s*)?(?:system\s+overview|overview|architecture|framework|implementation|design)\b[^\n]{0,120}",
    ),
)

SECTION_END_RE = (
    r"(^|\n)\s*(?:\d+(?:\.\d+)*\.?\s*)?"
    r"(?:experiments?|experimental\s+setup|evaluation|results?|analysis|discussion|limitations?|"
    r"conclusion|references|bibliography|appendix|acknowledg(?:e)?ments?)\b"
)


def plausible_heading(heading: str) -> bool:
    heading = clean_text(heading)
    if len(heading) < 3 or len(heading) > 160:
        return False
    if len(heading.split()) > 18:
        return False
    # Wrapped prose lines often end as full sentences; section headings usually do not.
    if heading.endswith(".") and len(heading) > 50:
        return False
    return True


def section_candidates(text: str, limit: int = 12) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    keywords = re.compile(
        r"\b(methodology|methods?|approach|workflow|pipeline|architecture|framework|system\s+overview|implementation|design)\b",
        flags=re.I,
    )
    for line in text.splitlines():
        heading = clean_text(line)
        key = heading.lower()
        if key in seen or not keywords.search(heading) or not plausible_heading(heading):
            continue
        candidates.append(heading)
        seen.add(key)
        if len(candidates) >= limit:
            break
    return candidates


def method_like_section(text: str) -> tuple[str, str, str]:
    for label, start_pattern in METHOD_LIKE_STARTS:
        for start in re.finditer(start_pattern, text, flags=re.I | re.M):
            heading = clean_text(start.group(0))
            if not plausible_heading(heading):
                continue
            end = re.search(SECTION_END_RE, text[start.end() :], flags=re.I | re.M)
            body = text[start.end() :] if not end else text[start.end() : start.end() + end.start()]
            body = clean_text(body)
            if len(body) >= 200:
                return body, heading, label
    return "", "", ""


def readpack(root: Path, query: str, max_pages: int) -> dict:
    pdf_path, match = resolve_pdf(root, query)
    if match is None:
        relative = str(pdf_path.relative_to(root)) if pdf_path.is_relative_to(root) else ""
        match = next((item for item in read_index(root) if str(item.get("path", "")) == relative), None)
    pages = extract_pdf_pages(pdf_path, max_pages=max_pages)
    full = "\n".join(pages)
    title = match.get("title") if match else extract_title_from_first_page(pages[0] if pages else "", pdf_path.stem)
    abstract = between(full, r"\bAbstract\b", r"\b(1\s+Introduction|Introduction|Keywords)\b")
    method, method_heading, method_label = method_like_section(full)
    appendix = between(full, r"(^|\n)\s*A\s+Instruction Templates\b", r"(^|\n)\s*B\s+")
    warnings = []
    if not abstract:
        warnings.append("abstract_not_found")
    if not method:
        warnings.append("method_not_found")
    return {
        "title": title,
        "path": str(pdf_path.relative_to(root) if pdf_path.is_relative_to(root) else pdf_path),
        "note_filename": note_filename(title),
        "abstract": abstract,
        "method_heading": method_heading,
        "method_label": method_label,
        "method_preview": method[:12000],
        "section_candidates": section_candidates(full),
        "appendix_preview": appendix[:8000],
        "warnings": warnings,
    }


def renderer_status() -> dict[str, bool]:
    try:
        import fitz  # noqa: F401

        pymupdf = True
    except ImportError:
        pymupdf = False
    try:
        import PIL  # noqa: F401

        pil = True
    except ImportError:
        pil = False
    return {
        "ghostscript": shutil.which("gs") is not None,
        "pymupdf": pymupdf,
        "pdftoppm": shutil.which("pdftoppm") is not None,
        "pil": pil,
    }


def parse_crop(crop: str) -> tuple[int, int, int, int]:
    parts = [part.strip() for part in crop.split(",")]
    if len(parts) != 4:
        raise WorkflowError("invalid_crop", "crop must be left,top,right,bottom")
    try:
        values = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise WorkflowError("invalid_crop", "crop coordinates must be integers") from exc
    left, top, right, bottom = values
    if left < 0 or top < 0 or right <= left or bottom <= top:
        raise WorkflowError("invalid_crop", "crop must satisfy 0 <= left < right and 0 <= top < bottom")
    return values


def render_page_with_ghostscript(pdf_path: Path, output: Path, page: int, dpi: int) -> None:
    gs = shutil.which("gs")
    if not gs:
        raise WorkflowError("pdf_renderer_missing", "Ghostscript is not available")
    command = [
        gs,
        "-dNOPAUSE",
        "-dBATCH",
        "-sDEVICE=pngalpha",
        f"-r{dpi}",
        f"-dFirstPage={page}",
        f"-dLastPage={page}",
        f"-sOutputFile={output}",
        str(pdf_path),
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise WorkflowError(
            "pdf_render_failed",
            f"failed to render page {page} with Ghostscript",
            {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]},
        )


def render_page_with_pymupdf(pdf_path: Path, output: Path, page: int, dpi: int) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise WorkflowError("pdf_renderer_missing", "PyMuPDF is not available") from exc
    try:
        doc = fitz.open(str(pdf_path))
        if page < 1 or page > len(doc):
            raise WorkflowError("invalid_page", f"page {page} is outside 1..{len(doc)}")
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pixmap = doc.load_page(page - 1).get_pixmap(matrix=matrix, alpha=True)
        pixmap.save(str(output))
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("pdf_render_failed", f"failed to render page {page} with PyMuPDF", str(exc)) from exc


def render_page_with_pdftoppm(pdf_path: Path, output: Path, page: int, dpi: int) -> None:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise WorkflowError("pdf_renderer_missing", "Poppler pdftoppm is not available")
    output_base = output.with_suffix("")
    command = [
        pdftoppm,
        "-f",
        str(page),
        "-l",
        str(page),
        "-r",
        str(dpi),
        "-png",
        "-singlefile",
        str(pdf_path),
        str(output_base),
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise WorkflowError(
            "pdf_render_failed",
            f"failed to render page {page} with pdftoppm",
            {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]},
        )
    generated = output_base.with_suffix(".png")
    if generated != output and generated.exists():
        generated.replace(output)
    if not output.exists():
        raise WorkflowError("pdf_render_failed", f"pdftoppm did not create {output}")


def scale_crop(crop: str, scale: float) -> str:
    if scale == 1:
        return crop
    left, top, right, bottom = parse_crop(crop)
    scaled = (
        round(left * scale),
        round(top * scale),
        round(right * scale),
        round(bottom * scale),
    )
    return ",".join(str(value) for value in scaled)


def auto_render_dpi(pdf_path: Path, page: int, crop: str | None) -> int:
    base_dpi = 180
    max_dpi = 360
    if crop:
        left, top, right, bottom = parse_crop(crop)
        shortest_edge = min(right - left, bottom - top)
        if shortest_edge <= 0:
            return base_dpi
        target_shortest_edge = 1100
        scale = max(1.0, target_shortest_edge / shortest_edge)
        return min(max_dpi, max(base_dpi, int(round(base_dpi * scale / 30) * 30)))

    # Whole-page screenshots are usually used as contextual figures in notes.
    # A modest bump keeps small text readable without producing very large files.
    return 240


def parse_dpi(pdf_path: Path, page: int, dpi: str, crop: str | None) -> tuple[int, float, bool]:
    if dpi == "auto":
        resolved = auto_render_dpi(pdf_path, page, crop)
        return resolved, resolved / 180, True
    try:
        resolved = int(dpi)
    except ValueError as exc:
        raise WorkflowError("invalid_dpi", "dpi must be an integer between 36 and 600, or 'auto'") from exc
    if resolved < 36 or resolved > 600:
        raise WorkflowError("invalid_dpi", "dpi must be between 36 and 600")
    return resolved, 1.0, False


def crop_image(path: Path, crop: str) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise WorkflowError("image_crop_dependency_missing", "Pillow is required for --crop") from exc
    box = parse_crop(crop)
    with Image.open(path) as image:
        image.crop(box).save(path)


def render_page(root: Path, query: str, page: int, output: Path | None, dpi: str, crop: str | None) -> dict:
    if page < 1:
        raise WorkflowError("invalid_page", "page must be >= 1")
    pdf_path, match = resolve_pdf(root, query)
    resolved_dpi, crop_scale, dpi_auto = parse_dpi(pdf_path, page, dpi, crop)
    title = match.get("title") if match else pdf_path.stem
    if output is None:
        stem = Path(note_filename(title)).stem
        output = workspace_path(root, Path("notes/assets") / f"{stem}_page{page}.png", "render output")
    else:
        output = workspace_path(root, output, "render output")
    output = unique_path(output)
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=".literature-render-", suffix=".png", dir=root)
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    temporary.unlink()

    try:
        status = renderer_status()
        if status["ghostscript"]:
            renderer = "ghostscript"
            render_page_with_ghostscript(pdf_path, temporary, page, resolved_dpi)
        elif status["pymupdf"]:
            renderer = "pymupdf"
            render_page_with_pymupdf(pdf_path, temporary, page, resolved_dpi)
        elif status["pdftoppm"]:
            renderer = "pdftoppm"
            render_page_with_pdftoppm(pdf_path, temporary, page, resolved_dpi)
        else:
            raise WorkflowError(
                "pdf_renderer_missing",
                "no PDF renderer available; install Ghostscript, PyMuPDF, or Poppler pdftoppm, or omit the screenshot",
                status,
            )
        if crop:
            crop_image(temporary, scale_crop(crop, crop_scale))
        move_file_without_overwrite(root, temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "output": str(output.relative_to(root) if output.is_relative_to(root) else output),
        "paper": str(pdf_path.relative_to(root) if pdf_path.is_relative_to(root) else pdf_path),
        "page": page,
        "dpi": resolved_dpi,
        "dpi_auto": dpi_auto,
        "renderer": renderer,
        "cropped": bool(crop),
    }


def cmd_refresh(args: argparse.Namespace) -> int:
    index = write_index(args.root)
    print(f"wrote {len(index)} entries to references/paper_index.jsonl")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    payload = setup_workspace(args.root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    matches = find_matches(args.root, args.query, args.limit)
    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
    else:
        for item in matches:
            kind = item.get("kind", "paper")
            print(f"{item['score']:.4f}\t{kind}\t{item_locator(item)}\t{item['title']}")
    return 0 if matches else 1


def cmd_add(args: argparse.Namespace) -> int:
    target = add_pdf(args.root, args.source, args.name)
    print(str(target.relative_to(args.root) if target.is_relative_to(args.root) else target))
    write_index(args.root)
    return 0


def cmd_organize(args: argparse.Namespace) -> int:
    rules = load_organization_rules(args.root, args.rules)
    planned = organization_items(args.root, rules)
    if args.apply:
        payload = apply_organization(args.root, planned)
    else:
        payload = {"dry_run": True, "moved": 0, "plan": planned, "index_entries": len(planned)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_readpack(args: argparse.Namespace) -> int:
    payload = readpack(args.root, args.query, args.max_pages)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_note_name(args: argparse.Namespace) -> int:
    print(note_filename(args.title))
    return 0


def cmd_render_page(args: argparse.Namespace) -> int:
    payload = render_page(args.root, args.query, args.page, args.output, args.dpi, args.crop)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    ensure_root(args.root)
    text_extractors = text_extractor_status()
    pdf_count = len(list((args.root / "papers").rglob("*.pdf"))) + len(list(args.root.glob("*.pdf")))
    index_path = args.root / "references/paper_index.jsonl"
    source_path = source_registry_path(args.root)
    status = {
        "root": str(args.root),
        "text_extractors": text_extractors,
        "renderers": renderer_status(),
        "pdf_count": pdf_count,
        "index_exists": index_path.exists(),
        "index_stale": index_is_stale(args.root, index_path),
        "bib_exists": (args.root / "references/references.bib").exists(),
        "source_registry_exists": source_path.exists(),
        "source_registry_records": len(load_source_records(args.root)) if source_path.exists() else 0,
        "survey_count": len(survey_manifest_paths(args.root)),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if any(text_extractors.values()) else 1


def cmd_source_init(args: argparse.Namespace) -> int:
    path = source_registry_path(args.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    print(str(path.relative_to(args.root)))
    return 0


def cmd_source_list(args: argparse.Namespace) -> int:
    records = load_source_records(args.root)
    if args.kind:
        records = [record for record in records if record.get("kind") == args.kind]
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for record in records:
            print(f"{record.get('id')}\t{record.get('kind', 'paper')}\t{len(record.get('sources', []))}\t{record.get('title')}")
    return 0


def cmd_source_add(args: argparse.Namespace) -> int:
    if args.kind not in SOURCE_KINDS:
        raise WorkflowError("invalid_kind", f"kind must be one of: {', '.join(sorted(SOURCE_KINDS))}")
    records = load_source_records(args.root)
    record_id = args.id or entity_id(args.title)
    idx, existing = find_source_record(records, args.title)
    sources = collect_sources(args)
    aliases = sorted({*(args.alias or []), *(existing.get("aliases", []) if existing else [])})

    record = existing or {"id": record_id, "title": args.title, "kind": args.kind, "aliases": [], "sources": []}
    record["id"] = str(record.get("id") or record_id)
    record["title"] = args.title
    record["kind"] = args.kind
    record["aliases"] = aliases
    record["sources"] = merge_source_lists(record.get("sources", []), sources)

    if idx is None:
        records.append(record)
    else:
        records[idx] = record
    write_source_records(args.root, records)
    write_index(args.root)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_source_link(args: argparse.Namespace) -> int:
    records = load_source_records(args.root)
    idx, record = find_source_record(records, args.query)
    if record is None:
        matches = find_matches(args.root, args.query, 5)
        if not matches:
            raise WorkflowError("no_match", f"no entity match: {args.query}")
        if len(matches) > 1 and matches[0]["score"] - matches[1]["score"] <= AMBIGUITY_MARGIN:
            raise WorkflowError("ambiguous_match", "entity query is ambiguous", matches)
        record = record_from_index_item(matches[0])
        idx = None

    sources = collect_sources(args)
    if not sources:
        raise WorkflowError("empty_source", "no source was provided")
    record["sources"] = merge_source_lists(record.get("sources", []), sources)
    if args.alias:
        record["aliases"] = sorted({*record.get("aliases", []), *args.alias})

    if idx is None:
        records.append(record)
    else:
        records[idx] = record
    write_source_records(args.root, records)
    write_index(args.root)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_source_show(args: argparse.Namespace) -> int:
    matches = find_matches(args.root, args.query, args.limit)
    if not matches:
        raise WorkflowError("no_match", f"no entity match: {args.query}")
    print(json.dumps(matches, ensure_ascii=False, indent=2))
    return 0


def cmd_survey_init(args: argparse.Namespace) -> int:
    payload = create_or_update_survey(args.root, args.title, args.scope, args.paper, args.source, args.update)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_survey_refresh(args: argparse.Namespace) -> int:
    payload = refresh_survey(args.root, args.query)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_survey_show(args: argparse.Namespace) -> int:
    manifest_path = resolve_survey_manifest(args.root, args.query)
    print(json.dumps(load_survey_manifest(manifest_path), ensure_ascii=False, indent=2))
    return 0


def cmd_survey_source_add(args: argparse.Namespace) -> int:
    path = resolve_local_document(args.root, args.path)
    if args.move:
        path = move_survey_source_document(args.root, path)
    record, source = ensure_survey_document_entity(args.root, path, args.title)
    payload = {
        "entity_id": record["id"],
        "title": record["title"],
        "source": source,
        "path": relative_locator(args.root, path),
        "moved": bool(args.move),
    }
    payload["index_entries"] = len(write_index(args.root))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pdf", action="append", default=[], help="local PDF path")
    parser.add_argument("--url", action="append", default=[], help="web URL")
    parser.add_argument("--arxiv", action="append", default=[], help="arXiv id or URL")
    parser.add_argument("--doi", action="append", default=[], help="DOI")
    parser.add_argument("--repo", action="append", default=[], help="repository URL")
    parser.add_argument("--doc", action="append", default=[], help="local documentation path")
    parser.add_argument("--source", action="append", default=[], help="generic source, optionally type=locator")
    parser.add_argument("--alias", action="append", default=[], help="extra title or method alias")


def handle_error(exc: Exception) -> int:
    if isinstance(exc, WorkflowError):
        payload = {"ok": False, "error": exc.code, "message": exc.message}
        if exc.details is not None:
            payload["details"] = exc.details
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    raise exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Local literature workflow.")
    parser.add_argument("--root", default=".", type=Path, help="workspace root")
    sub = parser.add_subparsers(dest="cmd", required=True)

    setup = sub.add_parser("setup", help="create the workspace folders, source registry, and index")
    setup.set_defaults(func=cmd_setup)

    refresh = sub.add_parser("refresh", help="rebuild paper index")
    refresh.set_defaults(func=cmd_refresh)

    find = sub.add_parser("find", help="find a local PDF")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    find.add_argument("--json", action="store_true")
    find.set_defaults(func=cmd_find)

    add = sub.add_parser("add", help="add a PDF to the root inbox, then refresh index")
    add.add_argument("source")
    add.add_argument("--name")
    add.set_defaults(func=cmd_add)

    organize = sub.add_parser(
        "organize",
        help="rename PDFs from their titles and place them into configured topic folders",
    )
    organize.add_argument("--rules", type=Path, help="organization rules JSON, relative to workspace root")
    organize.add_argument("--apply", action="store_true", help="apply the plan; without it, print a dry-run plan")
    organize.set_defaults(func=cmd_organize)

    pack = sub.add_parser("readpack", help="resolve PDF and extract abstract/method/workflow snippets")
    pack.add_argument("query")
    pack.add_argument("--max-pages", type=int, default=12)
    pack.set_defaults(func=cmd_readpack)

    note = sub.add_parser("note-name", help="normalize title to HTML note filename")
    note.add_argument("title")
    note.set_defaults(func=cmd_note_name)

    render = sub.add_parser("render-page", help="render one PDF page to a PNG asset")
    render.add_argument("query")
    render.add_argument("--page", type=int, required=True)
    render.add_argument("--output", type=Path)
    render.add_argument("--dpi", default="180", help="integer DPI, or 'auto' for note-friendly rendering")
    render.add_argument("--crop", help="optional pixel crop: left,top,right,bottom")
    render.set_defaults(func=cmd_render_page)

    doctor = sub.add_parser("doctor", help="check workflow dependencies and index status")
    doctor.set_defaults(func=cmd_doctor)

    source = sub.add_parser("source", help="manage entity/source registry")
    source_sub = source.add_subparsers(dest="source_cmd", required=True)

    source_init = source_sub.add_parser("init", help="create references/source_registry.jsonl")
    source_init.set_defaults(func=cmd_source_init)

    source_list = source_sub.add_parser("list", help="list registered paper/doc entities")
    source_list.add_argument("--kind", choices=sorted(SOURCE_KINDS))
    source_list.add_argument("--json", action="store_true")
    source_list.set_defaults(func=cmd_source_list)

    source_add = source_sub.add_parser("add", help="register a paper, tech doc, repo, or other source entity")
    source_add.add_argument("--title", required=True)
    source_add.add_argument("--kind", default="paper", choices=sorted(SOURCE_KINDS))
    source_add.add_argument("--id")
    add_source_args(source_add)
    source_add.set_defaults(func=cmd_source_add)

    source_link = source_sub.add_parser("link", help="attach one or more sources to an existing entity")
    source_link.add_argument("query")
    add_source_args(source_link)
    source_link.set_defaults(func=cmd_source_link)

    source_show = source_sub.add_parser("show", help="show indexed source metadata for a query")
    source_show.add_argument("query")
    source_show.add_argument("--limit", type=int, default=5)
    source_show.set_defaults(func=cmd_source_show)

    survey = sub.add_parser("survey", help="create and maintain a scoped literature-survey work pack")
    survey_sub = survey.add_subparsers(dest="survey_cmd", required=True)

    survey_init = survey_sub.add_parser("init", help="create a survey scope from selected papers and read-only source documents")
    survey_init.add_argument("--title", required=True)
    survey_init.add_argument("--scope", required=True, help="user-defined question, boundary, or intended narrative")
    survey_init.add_argument("--paper", action="append", default=[], help="selected local paper title, alias, or path; repeatable")
    survey_init.add_argument("--source", action="append", default=[], help="read-only local survey/source document; repeatable")
    survey_init.add_argument("--update", action="store_true", help="replace an existing generated survey scope list")
    survey_init.set_defaults(func=cmd_survey_init)

    survey_refresh = survey_sub.add_parser("refresh", help="refresh paths and availability in a generated survey scope")
    survey_refresh.add_argument("query", help="survey title or directory name")
    survey_refresh.set_defaults(func=cmd_survey_refresh)

    survey_show = survey_sub.add_parser("show", help="show a generated survey scope manifest")
    survey_show.add_argument("query", help="survey title or directory name")
    survey_show.set_defaults(func=cmd_survey_show)

    survey_source = survey_sub.add_parser("source", help="register a read-only survey source document")
    survey_source_sub = survey_source.add_subparsers(dest="survey_source_cmd", required=True)
    survey_source_add = survey_source_sub.add_parser("add", help="register a source document and optionally move it into surveys/sources")
    survey_source_add.add_argument("path")
    survey_source_add.add_argument("--title", help="optional display title; source bytes are never changed")
    survey_source_add.add_argument("--move", action="store_true", help="move an in-workspace source into surveys/sources without editing it")
    survey_source_add.set_defaults(func=cmd_survey_source_add)

    args = parser.parse_args()
    args.root = args.root.resolve()
    try:
        if args.cmd != "setup":
            recover_pending_organization(args.root)
        return args.func(args)
    except Exception as exc:
        return handle_error(exc)


if __name__ == "__main__":
    raise SystemExit(main())
