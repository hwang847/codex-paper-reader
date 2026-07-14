#!/usr/bin/env python3
"""Build a title/alias/arXiv-id to local PDF index."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


SOURCE_REGISTRY = Path("references/source_registry.jsonl")
LOCAL_SOURCE_TYPES = {"pdf", "doc", "html", "text", "path"}
PDF_GLOB = "*.[pP][dD][fF]"


def clean_bib_value(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if (value.startswith("{") and value.endswith("}")) or (
        value.startswith('"') and value.endswith('"')
    ):
        value = value[1:-1]
    value = re.sub(r"[{}]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(text: str) -> str:
    value = normalize(text).replace(" ", "_")
    return value or "untitled"


def method_alias(title: str) -> str | None:
    if ":" not in title:
        return None
    head = title.split(":", 1)[0].strip()
    if not head or len(head.split()) > 4:
        return None
    if re.search(r"[A-Z]{2,}|[-_]", head) or head[:1].isupper():
        return head
    return None


def entity_id(title: str) -> str:
    return slug(method_alias(title) or title)


def path_within_root(root: Path, path: Path, label: str) -> Path:
    root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside workspace root: {path}") from exc
    return resolved


def load_source_registry(root: Path) -> list[dict[str, object]]:
    path = path_within_root(root, root / SOURCE_REGISTRY, "source registry")
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}:{line_no}: {exc}") from exc
        if not raw.get("title"):
            raise ValueError(f"source registry record missing title in {path}:{line_no}")
        raw.setdefault("id", entity_id(str(raw["title"])))
        raw.setdefault("kind", "paper")
        raw.setdefault("aliases", [])
        raw.setdefault("sources", [])
        records.append(raw)
    return records


def local_source_path(root: Path, source: dict[str, object]) -> Path | None:
    locator = str(source.get("locator", "")).strip()
    if not locator or str(source.get("type", "")).lower() not in LOCAL_SOURCE_TYPES:
        return None
    parsed = urlparse(locator)
    if parsed.scheme in {"http", "https"}:
        return None
    path = Path(locator).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def source_aliases(source: dict[str, object]) -> list[str]:
    locator = str(source.get("locator", "")).strip()
    if not locator:
        return []
    aliases = [locator]
    parsed = urlparse(locator)
    if parsed.scheme in {"http", "https"}:
        name = Path(parsed.path).name
        if name:
            aliases.extend([name, Path(name).stem])
        arxiv = re.search(r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?", locator)
        if arxiv:
            aliases.append(arxiv.group(0))
            aliases.append(f"arXiv:{arxiv.group(0)}")
    else:
        aliases.extend([Path(locator).name, Path(locator).stem])
    if str(source.get("type", "")).lower() == "arxiv":
        aliases.append(f"arXiv:{locator}")
    return sorted({alias for alias in aliases if alias})


def registry_aliases(record: dict[str, object]) -> list[str]:
    title = str(record.get("title", ""))
    aliases = [title, str(record.get("id", ""))]
    aliases.extend(str(alias) for alias in record.get("aliases", []) if alias)
    alias = method_alias(title)
    if alias:
        aliases.append(alias)
    for source in record.get("sources", []):
        if isinstance(source, dict):
            aliases.extend(source_aliases(source))
    return sorted({alias for alias in aliases if alias})


def source_key(source: dict[str, object]) -> str:
    return f"{str(source.get('type', '')).lower()}:{str(source.get('locator', '')).strip().lower()}"


def merge_sources(existing: list[dict[str, object]], incoming: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in [*existing, *incoming]:
        key = source_key(source)
        if not key or key in seen:
            continue
        merged.append(source)
        seen.add(key)
    return merged


def auto_sources(record: dict[str, str], pdf_path: Path, root: Path) -> list[dict[str, object]]:
    rel = str(pdf_path.relative_to(root))
    sources: list[dict[str, object]] = [
        {"type": "pdf", "locator": rel, "role": "primary", "status": "available"}
    ]
    if record.get("eprint"):
        sources.append({"type": "arxiv", "locator": record["eprint"], "role": "identifier", "status": "external"})
    if record.get("doi"):
        sources.append({"type": "doi", "locator": record["doi"], "role": "identifier", "status": "external"})
    if record.get("url"):
        sources.append({"type": "url", "locator": record["url"], "role": "landing", "status": "external"})
    return sources


def preferred_pdf_path(root: Path, sources: list[dict[str, object]]) -> str | None:
    candidates = sorted(
        sources,
        key=lambda source: 0 if source.get("role") == "primary" else 1,
    )
    for source in candidates:
        if str(source.get("type", "")).lower() != "pdf":
            continue
        path = local_source_path(root, source)
        if path and path.exists():
            try:
                return str(path.relative_to(root))
            except ValueError:
                return str(path)
    return None


def merge_source_registry(root: Path, index: list[dict[str, object]]) -> list[dict[str, object]]:
    registry = load_source_registry(root)
    if not registry:
        return index

    by_path: dict[str, dict[str, object]] = {}
    by_title: dict[str, dict[str, object]] = {}
    by_source: dict[str, dict[str, object]] = {}
    for item in index:
        if item.get("path"):
            by_path[str(item["path"])] = item
        by_title[normalize(str(item.get("title", "")))] = item
        for source in item.get("sources", []):
            if isinstance(source, dict):
                by_source[source_key(source)] = item

    for record in registry:
        sources = [source for source in record.get("sources", []) if isinstance(source, dict)]
        target: dict[str, object] | None = None
        for source in sources:
            local_path = local_source_path(root, source)
            if local_path:
                try:
                    rel = str(local_path.relative_to(root))
                except ValueError:
                    rel = str(local_path)
                target = by_path.get(rel)
            if not target:
                target = by_source.get(source_key(source))
            if target:
                break
        if not target:
            target = by_title.get(normalize(str(record.get("title", ""))))

        aliases = registry_aliases(record)
        if target:
            target["entity_id"] = record.get("id") or target.get("entity_id")
            target["kind"] = record.get("kind") or target.get("kind", "paper")
            target["title"] = record.get("title") or target.get("title")
            target["aliases"] = sorted({*target.get("aliases", []), *aliases})
            target["normalized_aliases"] = [normalize(alias) for alias in target["aliases"]]
            target["sources"] = merge_sources(target.get("sources", []), sources)
            target["source_count"] = len(target["sources"])
            target["source_type"] = "source_registry"
            path = preferred_pdf_path(root, target["sources"])
            if path:
                target["path"] = path
            continue

        path = preferred_pdf_path(root, sources)
        item: dict[str, object] = {
            "title": str(record["title"]),
            "entity_id": str(record.get("id") or entity_id(str(record["title"]))),
            "kind": str(record.get("kind", "paper")),
            "aliases": aliases,
            "normalized_aliases": [normalize(alias) for alias in aliases],
            "sources": sources,
            "source_count": len(sources),
            "source_type": "source_registry",
        }
        if path:
            item["path"] = path
        index.append(item)

    return index


def parse_field(entry: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*", entry, flags=re.I)
    if not match:
        return None
    i = match.end()
    while i < len(entry) and entry[i].isspace():
        i += 1
    if i >= len(entry):
        return None

    opener = entry[i]
    if opener in "{[":
        closer = "}" if opener == "{" else "]"
        depth = 0
        start = i
        for j in range(i, len(entry)):
            if entry[j] == opener:
                depth += 1
            elif entry[j] == closer:
                depth -= 1
                if depth == 0:
                    return clean_bib_value(entry[start : j + 1])
        return None

    if opener == '"':
        start = i
        j = i + 1
        while j < len(entry):
            if entry[j] == '"' and entry[j - 1] != "\\":
                return clean_bib_value(entry[start : j + 1])
            j += 1
        return None

    end = entry.find(",", i)
    if end == -1:
        end = len(entry)
    return clean_bib_value(entry[i:end])


def parse_bib_entries(bib_path: Path) -> list[dict[str, str]]:
    if not bib_path.exists():
        return []

    entries: list[dict[str, str]] = []
    lines = bib_path.read_text(encoding="utf-8").splitlines()
    source: str | None = None
    current: list[str] | None = None
    current_source: str | None = None
    depth = 0

    for line in lines:
        source_match = re.match(r"\s*%\s*Source:\s*(.+?)\s*$", line)
        if source_match and current is None:
            source = source_match.group(1).strip()
            continue

        if current is None and line.lstrip().startswith("@"):
            current = [line]
            current_source = source
            source = None
            depth = line.count("{") - line.count("}")
            if depth <= 0:
                entry = "\n".join(current)
                entries.append(entry_to_record(entry, current_source))
                current = None
            continue

        if current is not None:
            current.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                entry = "\n".join(current)
                entries.append(entry_to_record(entry, current_source))
                current = None

    return [entry for entry in entries if entry.get("title")]


def entry_to_record(entry: str, source: str | None) -> dict[str, str]:
    key_match = re.match(r"\s*@(?P<type>\w+)\s*{\s*(?P<key>[^,\s]+)", entry)
    record: dict[str, str] = {}
    if key_match:
        record["bibtex_type"] = key_match.group("type")
        record["bibtex_key"] = key_match.group("key")
    if source:
        record["source"] = source
    for field in ("title", "author", "year", "eprint", "url", "doi"):
        value = parse_field(entry, field)
        if value:
            record[field] = value
    return record


def clean_pdf_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def looks_generic_title(title: str) -> bool:
    normalized = normalize(title)
    if len(normalized) < 4:
        return True
    generic_exact = {
        "untitled",
        "paper",
        "microsoft word",
        "conference acronym",
        "arxiv",
    }
    generic_prefixes = (
        "untitled ",
        "microsoft word",
        "conference acronym",
        "arxiv",
        "published as a conference paper",
        "findings of the association for computational linguistics",
        "proceedings of the ",
        "association for computational linguistics",
    )
    return normalized in generic_exact or normalized.startswith(generic_prefixes)


def title_preamble_line(line: str) -> bool:
    normalized = normalize(line)
    if looks_generic_title(line):
        return True
    return (
        "association for computational linguistics" in normalized
        or normalized.startswith("permission to make")
        or normalized.startswith("copyright ")
    )


def author_or_affiliation_line(line: str) -> bool:
    if "@" in line:
        return True
    if re.search(r"\b(university|institute|college|school|laboratory|department|inc)\b", line, re.I):
        return True
    if re.search(r"\b[A-Z][A-Za-z'`-]+(?:\s+[A-Z][A-Za-z'`-]+){1,3}\d", line):
        return True
    names = re.findall(r"\b[A-Z][a-z]+(?:[-'][A-Za-z]+)?\b", line)
    return line.count(",") >= 2 and len(names) >= 4


def extract_pdf_title(pdf_path: Path) -> str | None:
    text = ""
    try:
        from pypdf import PdfReader

        logger = logging.getLogger("pypdf")
        previous_level = logger.level
        logger.setLevel(logging.ERROR)
        try:
            reader = PdfReader(str(pdf_path))
            metadata_title = clean_pdf_text(str(reader.metadata.title or ""))
            if metadata_title and not looks_generic_title(metadata_title):
                return metadata_title

            text = reader.pages[0].extract_text() or ""
        finally:
            logger.setLevel(previous_level)
    except Exception:
        text = ""

    if not text and shutil.which("pdftotext"):
        result = subprocess.run(
            [shutil.which("pdftotext") or "pdftotext", "-f", "1", "-l", "1", str(pdf_path), "-"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            text = result.stdout

    lines = [clean_pdf_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line and not re.fullmatch(r"\d+", line)]
    lines = [line for line in lines[:20] if not title_preamble_line(line)]
    if not lines:
        return None

    title = lines[0]
    joiners = {"a", "an", "the", "of", "for", "to", "via", "with", "and", "or", "in", "on"}
    for line in lines[1:4]:
        if author_or_affiliation_line(line):
            break
        previous_last = title.split()[-1].lower().strip(":,")
        should_join = previous_last in joiners or len(title) < 80 or title.endswith(("-", ":", "for"))
        if not should_join:
            break
        candidate = f"{title} {line}"
        if len(candidate) > 220:
            break
        title = candidate

    title = clean_pdf_text(title)
    return None if looks_generic_title(title) else title


def library_pdfs(root: Path) -> list[Path]:
    papers_dir = path_within_root(root, root / "papers", "papers directory")
    candidates = list(papers_dir.rglob(PDF_GLOB)) if papers_dir.exists() else []
    candidates.extend(root.glob(PDF_GLOB))
    safe_paths = []
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            safe_paths.append(path_within_root(root, path, "PDF path"))
        except ValueError:
            continue
    return sorted(set(safe_paths))


def registered_workspace_pdfs(root: Path) -> list[Path]:
    """Return regular workspace PDFs explicitly registered outside library folders."""
    root = root.resolve()
    paths: set[Path] = set()
    for record in load_source_registry(root):
        for source in record.get("sources", []):
            if not isinstance(source, dict) or str(source.get("type", "")).lower() != "pdf":
                continue
            locator = str(source.get("locator", "")).strip()
            if not locator or urlparse(locator).scheme in {"http", "https"}:
                continue
            lexical = Path(locator).expanduser()
            if not lexical.is_absolute():
                lexical = root / lexical
            if lexical.is_symlink():
                continue
            try:
                path = path_within_root(root, lexical, "registered PDF path")
            except ValueError:
                continue
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def workspace_pdfs(root: Path) -> list[Path]:
    """Return every safe local PDF that can appear in the generated index."""
    return sorted({*library_pdfs(root), *registered_workspace_pdfs(root)})


def pdf_map(root: Path) -> dict[str, Path]:
    return {path.name: path for path in library_pdfs(root)}


def record_aliases(record: dict[str, str], pdf_name: str) -> list[str]:
    aliases = [record["title"], Path(pdf_name).stem]
    alias = method_alias(record["title"])
    if alias:
        aliases.append(alias)
    if record.get("eprint"):
        aliases.append(record["eprint"])
        aliases.append(f"arXiv:{record['eprint']}")
    return sorted({alias for alias in aliases if alias})


def build_index(root: Path, bib_path: Path) -> list[dict[str, object]]:
    root = root.resolve()
    bib_path = path_within_root(root, bib_path, "BibTeX path")
    pdfs = pdf_map(root)
    records = parse_bib_entries(bib_path)
    index: list[dict[str, object]] = []
    indexed_paths: set[Path] = set()

    for record in records:
        source = record.get("source")
        pdf_path = pdfs.get(Path(source).name) if source else None
        if not pdf_path and record.get("eprint"):
            for name, candidate in pdfs.items():
                if name.startswith(record["eprint"]):
                    pdf_path = candidate
                    break
        if not pdf_path:
            continue

        aliases = record_aliases(record, pdf_path.name)
        sources = auto_sources(record, pdf_path, root)
        item = {
            "title": record["title"],
            "entity_id": entity_id(record["title"]),
            "kind": "paper",
            "aliases": aliases,
            "normalized_aliases": [normalize(alias) for alias in aliases],
            "path": str(pdf_path.relative_to(root)),
            "sources": sources,
            "source_count": len(sources),
            "source": source or pdf_path.name,
            "source_type": "bibtex",
        }
        for field in ("author", "year", "eprint", "url", "doi", "bibtex_key"):
            if record.get(field):
                item[field] = record[field]
        index.append(item)
        indexed_paths.add(pdf_path.resolve())

    for pdf_path in library_pdfs(root):
        if pdf_path.resolve() in indexed_paths:
            continue
        extracted_title = extract_pdf_title(pdf_path)
        title = extracted_title or pdf_path.stem
        aliases = sorted({title, pdf_path.name, pdf_path.stem})
        rel = str(pdf_path.relative_to(root))
        index.append(
            {
                "title": title,
                "entity_id": entity_id(title),
                "kind": "paper",
                "aliases": aliases,
                "normalized_aliases": [normalize(alias) for alias in aliases],
                "path": rel,
                "sources": [{"type": "pdf", "locator": rel, "role": "primary", "status": "available"}],
                "source_count": 1,
                "source": pdf_path.name,
                "source_type": "pdf_inbox" if pdf_path.parent == root else "pdf_orphan",
                "title_source": "pdf_text_or_metadata" if extracted_title else "filename",
            }
        )

    index = merge_source_registry(root, index)
    index.sort(key=lambda item: (str(item.get("title", "")).lower(), str(item.get("path", ""))))
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build references/paper_index.jsonl.")
    parser.add_argument("--root", default=".", help="literature workspace root")
    parser.add_argument("--bib", default="references/references.bib", help="BibTeX file")
    parser.add_argument("--output", default="references/paper_index.jsonl", help="JSONL output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"workspace root is not a directory: {root}")
    try:
        bib_path = path_within_root(root, root / args.bib, "BibTeX path")
        output = path_within_root(root, root / args.output, "output path")
    except ValueError as exc:
        parser.error(str(exc))
    index = build_index(root, bib_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in index) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(index)} entries to {output.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
