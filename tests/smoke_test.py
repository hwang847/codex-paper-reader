#!/usr/bin/env python3
"""Smoke-test the literature workflow skill without external dependencies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "paper_workflow.py"
sys.path.insert(0, str(ROOT / "scripts"))

from build_paper_index import looks_generic_title  # noqa: E402
from paper_workflow import classify_paper, method_like_section, resolve_pdf, section_candidates  # noqa: E402


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-B", str(TOOL), *args],
        cwd=str(cwd or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def main() -> int:
    sample_text = """
Abstract
This paper studies retrieval.

1 Introduction
Intro text.

2 Related Work
Prior systems.

3 GroupRAG Workflow
The workflow first builds a graph index from document chunks and entities. It then performs
community-aware retrieval, expands the query context with graph neighborhoods, and composes
evidence for generation. The controller keeps intermediate state, retrieved nodes, selected
communities, and final evidence passages so the answer can be traced through the pipeline.

4 Experiments
Results follow.
"""
    method, heading, label = method_like_section(sample_text)
    assert label == "workflow"
    assert heading == "3 GroupRAG Workflow"
    assert "community-aware retrieval" in method
    assert "3 GroupRAG Workflow" in section_candidates(sample_text)
    assert looks_generic_title("Findings of the Association for Computational Linguistics: ACL 2025")
    assert looks_generic_title("Proceedings of the 64th Annual Meeting of the Association for Computational Linguistics")
    assert not looks_generic_title("What Paper Titles Teach Us About Reliable Indexing")
    gated_rules = {
        "default_category": "general-rl",
        "categories": [
            {
                "name": "text2sql-rl",
                "keywords": ["reinforcement"],
                "requires_any": ["text-to-sql", "text to sql"],
            },
            {"name": "general-rl", "keywords": ["reinforcement"]},
        ],
    }
    text2sql_category, _ = classify_paper(
        {"aliases": []},
        "Reinforcement Learning for Text-to-SQL",
        gated_rules,
        "text_rl.pdf",
    )
    general_category, _ = classify_paper(
        {"aliases": []},
        "Reinforcement Learning for Language Agents",
        gated_rules,
        "agent_rl.pdf",
    )
    assert text2sql_category == "text2sql-rl"
    assert general_category == "general-rl"
    strict_rules = {
        "default_category": "general-rl",
        "categories": [
            {
                "name": "trace-rl",
                "keywords": ["reinforcement"],
                "requires_any": ["text-to-sql"],
                "requires_all": ["reinforcement", "trace"],
            },
            {"name": "general-rl", "keywords": ["reinforcement"]},
        ],
    }
    trace_category, _ = classify_paper(
        {"aliases": []},
        "Reinforcement Learning from a Text-to-SQL Trace",
        strict_rules,
        "trace_rl.pdf",
    )
    missing_requirement_category, _ = classify_paper(
        {"aliases": []},
        "Reinforcement Learning for Text-to-SQL",
        strict_rules,
        "plain_rl.pdf",
    )
    assert trace_category == "trace-rl"
    assert missing_requirement_category == "general-rl"

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        setup = json.loads(run("--root", str(workspace), "setup").stdout)
        assert workspace.is_dir()
        assert (workspace / "papers").is_dir()
        assert (workspace / "notes" / "assets").is_dir()
        assert (workspace / "references" / "source_registry.jsonl").is_file()
        assert (workspace / "references" / "organization_rules.json").is_file()
        assert setup["index_entries"] == 0

        (workspace / "2501.00001v1.pdf").write_bytes(b"%PDF-1.4\n% smoke test placeholder\n")

        run("--root", str(workspace), "refresh")

        found = run("--root", str(workspace), "find", "2501.00001v1", "--json").stdout
        matches = json.loads(found)
        assert matches, "expected a PDF match"
        assert matches[0]["path"] == "2501.00001v1.pdf"

        registry = workspace / "references" / "source_registry.jsonl"
        registry.write_text(
            json.dumps(
                {
                    "title": "Human Friendly Title",
                    "kind": "paper",
                    "aliases": ["HFT"],
                    "sources": [
                        {
                            "type": "pdf",
                            "locator": "2501.00001v1.pdf",
                            "role": "primary",
                            "status": "available",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        future = time.time() + 2
        os.utime(registry, (future, future))

        refreshed_by_registry = run("--root", str(workspace), "find", "HFT", "--json").stdout
        registry_matches = json.loads(refreshed_by_registry)
        assert registry_matches and registry_matches[0]["title"] == "Human Friendly Title"

        note_name = run("--root", str(workspace), "note-name", "LinkAlign: Example Paper").stdout.strip()
        assert note_name == "linkalign.html"

        survey_source = workspace / "integrated_survey.md"
        survey_source_bytes = b"# Existing Survey\n\nThis source draft must stay byte-for-byte unchanged.\n"
        survey_source.write_bytes(survey_source_bytes)
        moved_source = json.loads(
            run(
                "--root",
                str(workspace),
                "survey",
                "source",
                "add",
                "integrated_survey.md",
                "--move",
            ).stdout
        )
        assert moved_source["moved"] is True
        assert (workspace / moved_source["path"]).read_bytes() == survey_source_bytes
        assert not survey_source.exists()
        non_pdf_read = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(workspace), "readpack", moved_source["title"]],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert non_pdf_read.returncode == 2
        assert "no_pdf_source" in non_pdf_read.stderr

        scoped = json.loads(
            run(
                "--root",
                str(workspace),
                "survey",
                "init",
                "--title",
                "Example Survey",
                "--scope",
                "Compare local paper retrieval and source management.",
                "--paper",
                "HFT",
                "--source",
                moved_source["path"],
            ).stdout
        )
        assert (workspace / scoped["manifest"]).is_file()
        assert (workspace / scoped["reading_pack"]).is_file()
        manifest = json.loads((workspace / scoped["manifest"]).read_text(encoding="utf-8"))
        assert manifest["papers"][0]["title"] == "Human Friendly Title"
        assert manifest["source_documents"][0]["source"]["status"] == "available"
        refreshed_survey = json.loads(run("--root", str(workspace), "survey", "refresh", "Example Survey").stdout)
        assert refreshed_survey["missing_papers"] == 0
        assert (workspace / moved_source["path"]).read_bytes() == survey_source_bytes

        organized = Path(tmp) / "organized"
        organized.mkdir()
        run("--root", str(organized), "setup")
        (organized / "download.pdf").write_bytes(b"%PDF-1.4\n% smoke test placeholder\n")
        (organized / "references" / "organization_rules.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_category": "uncategorized",
                    "categories": [
                        {"name": "core", "keywords": ["text-to-sql"]},
                        {"name": "uncategorized", "keywords": []},
                    ],
                    "title_overrides": {"download.pdf": "Example Text-to-SQL Paper"},
                    "category_overrides": {},
                }
            ),
            encoding="utf-8",
        )
        (organized / "references" / "references.bib").write_text(
            "% Source: download.pdf\n"
            "@article{example,\n"
            "  title = {Example Text-to-SQL Paper},\n"
            "  note = {download.pdf must not be globally rewritten}\n"
            "}\n",
            encoding="utf-8",
        )
        (organized / "references" / "source_registry.jsonl").write_text(
            json.dumps(
                {
                    "title": "Example Text-to-SQL Paper",
                    "kind": "paper",
                    "sources": [
                        {
                            "type": "pdf",
                            "locator": "download.pdf",
                            "role": "primary",
                            "status": "available",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        source_draft = organized / "draft.md"
        source_draft_bytes = b"# Existing Draft\n\nKeep the literal path download.pdf unchanged.\n"
        source_draft.write_bytes(source_draft_bytes)
        run("--root", str(organized), "survey", "source", "add", "draft.md")
        organization_scope = json.loads(
            run(
                "--root",
                str(organized),
                "survey",
                "init",
                "--title",
                "Organization Survey",
                "--scope",
                "Check path migration without rewriting source prose.",
                "--paper",
                "Example Text-to-SQL Paper",
                "--source",
                "draft.md",
            ).stdout
        )
        organized_plan = json.loads(run("--root", str(organized), "organize").stdout)
        assert organized_plan["plan"][0]["target"] == "papers/core/example_text_to_sql_paper.pdf"
        run("--root", str(organized), "organize", "--apply")
        assert (organized / "papers/core/example_text_to_sql_paper.pdf").is_file()
        assert not (organized / "download.pdf").exists()
        bib = (organized / "references" / "references.bib").read_text(encoding="utf-8")
        assert "% Source: example_text_to_sql_paper.pdf" in bib
        assert "note = {download.pdf must not be globally rewritten}" in bib
        source_records = [
            json.loads(line)
            for line in (organized / "references" / "source_registry.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        source_record = next(record for record in source_records if record["title"] == "Example Text-to-SQL Paper")
        assert source_record["sources"][0]["locator"] == "papers/core/example_text_to_sql_paper.pdf"
        assert json.loads(run("--root", str(organized), "find", "Example Text-to-SQL Paper", "--json").stdout)[0]["path"] == "papers/core/example_text_to_sql_paper.pdf"
        resolved, resolved_item = resolve_pdf(organized, "Example Text-to-SQL Paper")
        assert resolved == (organized / "papers/core/example_text_to_sql_paper.pdf").resolve()
        assert resolved_item and resolved_item["title"] == "Example Text-to-SQL Paper"
        assert source_draft.read_bytes() == source_draft_bytes
        organization_manifest = (organized / organization_scope["manifest"]).read_text(encoding="utf-8")
        organization_pack = (organized / organization_scope["reading_pack"]).read_text(encoding="utf-8")
        assert "papers/core/example_text_to_sql_paper.pdf" in organization_manifest
        assert "papers/core/example_text_to_sql_paper.pdf" in organization_pack

        invalid_rules = Path(tmp) / "invalid_rules.json"
        invalid_rules.write_text(
            json.dumps({"categories": [{"name": "../escape", "keywords": []}]}),
            encoding="utf-8",
        )
        rejected = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(organized), "organize", "--rules", str(invalid_rules)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert rejected.returncode == 2
        assert "invalid_organization_rules" in rejected.stderr

        run(
            "--root",
            str(workspace),
            "source",
            "add",
            "--kind",
            "tech_doc",
            "--title",
            "Example System Documentation",
            "--url",
            "https://example.com/docs",
            "--repo",
            "https://github.com/example/project",
            "--alias",
            "ESD",
        )

        shown = run("--root", str(workspace), "source", "show", "ESD").stdout
        items = json.loads(shown)
        assert items and items[0]["kind"] == "tech_doc"
        assert items[0]["source_count"] == 2

    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
