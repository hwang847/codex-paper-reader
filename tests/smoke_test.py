#!/usr/bin/env python3
"""Smoke-test the literature workflow skill without external dependencies."""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "paper_workflow.py"
INDEX_TOOL = ROOT / "scripts" / "build_paper_index.py"
sys.path.insert(0, str(ROOT / "scripts"))

import paper_workflow as workflow  # noqa: E402
from build_paper_index import looks_generic_title  # noqa: E402
from paper_workflow import (  # noqa: E402
    WorkflowError,
    apply_organization,
    classify_paper,
    load_organization_rules,
    method_like_section,
    organization_items,
    resolve_pdf,
    section_candidates,
)


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


class FakeDownloadResponse:
    def __init__(self, body: bytes, content_length: int | None = None) -> None:
        self._stream = io.BytesIO(body)
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> "FakeDownloadResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeDownloadOpener:
    def __init__(self, response: FakeDownloadResponse) -> None:
        self.response = response
        self.requests: list[object] = []

    def open(self, request: object, timeout: float) -> FakeDownloadResponse:
        self.requests.append((request, timeout))
        return self.response


def assert_pinned_download_boundaries(workspace: Path) -> None:
    public_address = "8.8.8.8"
    port = 8080
    url = f"http://rebind.invalid:{port}/paper.pdf"
    pdf = b"%PDF-1.4\n% download test\n"

    def fake_getaddrinfo(host: str, requested_port: int, *args: object, **kwargs: object):
        assert host == "rebind.invalid"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (public_address, requested_port))]

    with patch.object(workflow.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
        addresses = workflow.validate_download_url(url)
    assert addresses == (public_address,)
    for unsafe_address in ("127.0.0.1", "224.0.0.1", "fec0::1", "ff02::1", "64:ff9b::7f00:1"):
        assert not workflow.is_public_download_address(unsafe_address)

    connection = workflow.PinnedHTTPConnection(f"rebind.invalid:{port}", address=public_address)
    with patch.object(workflow.socket, "create_connection") as connect:
        connection.connect()
    connect.assert_called_once_with((public_address, port), connection.timeout, connection.source_address)

    tls_context = Mock()
    tls_context.check_hostname = False
    raw_socket = object()
    wrapped_socket = object()
    tls_context.wrap_socket.return_value = wrapped_socket
    tls_connection = workflow.PinnedHTTPSConnection(
        f"rebind.invalid:{port}",
        address=public_address,
        context=tls_context,
    )
    with patch.object(workflow.socket, "create_connection", return_value=raw_socket) as connect:
        tls_connection.connect()
    connect.assert_called_once_with((public_address, port), tls_connection.timeout, tls_connection.source_address)
    tls_context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="rebind.invalid")
    assert tls_connection.sock is wrapped_socket

    def download_with_response(target: Path, response: FakeDownloadResponse, limit: int | None = None) -> FakeDownloadOpener:
        opener = FakeDownloadOpener(response)
        limit_patch = patch.object(workflow, "MAX_DOWNLOAD_BYTES", limit) if limit is not None else None
        with patch.object(workflow.socket, "getaddrinfo", side_effect=fake_getaddrinfo), patch.object(
            workflow, "build_opener", return_value=opener
        ):
            if limit_patch is None:
                workflow.download(workspace, url, target)
            else:
                with limit_patch:
                    workflow.download(workspace, url, target)
        return opener

    target = workspace / "pinned.pdf"
    opener = download_with_response(target, FakeDownloadResponse(pdf, len(pdf)))
    assert target.read_bytes() == pdf
    assert opener.requests

    existing = b"%PDF-1.4\n% existing target\n"
    target.write_bytes(existing)
    try:
        download_with_response(target, FakeDownloadResponse(pdf, len(pdf)))
    except WorkflowError as exc:
        assert exc.code == "target_conflict"
    else:
        raise AssertionError("expected download finalization to preserve an existing target")
    assert target.read_bytes() == existing

    try:
        workflow.RejectRedirects().redirect_request(None, None, 302, "Found", {}, "/paper.pdf")
    except WorkflowError as exc:
        assert exc.code == "download_redirect_blocked"
    else:
        raise AssertionError("expected download redirect to be blocked")

    too_large_target = workspace / "too-large.pdf"
    try:
        download_with_response(too_large_target, FakeDownloadResponse(pdf, None), limit=10)
    except WorkflowError as exc:
        assert exc.code == "download_too_large"
    else:
        raise AssertionError("expected streamed download size to be enforced")
    assert not too_large_target.exists()

    non_pdf_target = workspace / "not-a-pdf.pdf"
    try:
        download_with_response(non_pdf_target, FakeDownloadResponse(b"not a PDF", 9))
    except WorkflowError as exc:
        assert exc.code == "download_not_pdf"
    else:
        raise AssertionError("expected non-PDF download to be rejected")
    assert not non_pdf_target.exists()
    assert not list(workspace.glob(".literature-download-*.pdf"))


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
        (workspace / "UPPER.PDF").write_bytes(b"%PDF-1.4\n% uppercase extension\n")

        outside_pdf = Path(tmp) / "outside.pdf"
        outside_pdf_bytes = b"%PDF-1.4\n% outside workspace\n"
        outside_pdf.write_bytes(outside_pdf_bytes)
        try:
            resolve_pdf(workspace, str(outside_pdf))
        except WorkflowError as exc:
            assert exc.code == "workspace_path_escape"
        else:
            raise AssertionError("expected direct PDF reads outside the workspace to be rejected")
        (workspace / "outside-link.pdf").symlink_to(outside_pdf)
        try:
            resolve_pdf(workspace, "outside-link.pdf")
        except WorkflowError as exc:
            assert exc.code == "workspace_path_escape"
        else:
            raise AssertionError("expected symlinked PDF reads outside the workspace to be rejected")
        local_copy_link = workspace / "local-copy.pdf"
        local_copy_link.symlink_to(outside_pdf)
        try:
            workflow.copy_file_without_overwrite(workspace, outside_pdf, local_copy_link)
        except WorkflowError as exc:
            assert exc.code in {"target_conflict", "workspace_path_escape"}
        else:
            raise AssertionError("expected local import to preserve an existing symlink target")
        assert outside_pdf.read_bytes() == outside_pdf_bytes

        run("--root", str(workspace), "refresh")

        found = run("--root", str(workspace), "find", "2501.00001v1", "--json").stdout
        matches = json.loads(found)
        assert matches, "expected a PDF match"
        assert matches[0]["path"] == "2501.00001v1.pdf"
        uppercase_matches = json.loads(run("--root", str(workspace), "find", "UPPER", "--json").stdout)
        assert uppercase_matches and uppercase_matches[0]["path"] == "UPPER.PDF"
        preserved_timestamp_pdf = workspace / "ARCHIVED.PDF"
        preserved_timestamp_pdf.write_bytes(b"%PDF-1.4\n% copied with an old timestamp\n")
        index_mtime = (workspace / "references" / "paper_index.jsonl").stat().st_mtime
        os.utime(preserved_timestamp_pdf, (index_mtime - 60, index_mtime - 60))
        preserved_timestamp_matches = json.loads(run("--root", str(workspace), "find", "ARCHIVED", "--json").stdout)
        assert preserved_timestamp_matches and preserved_timestamp_matches[0]["path"] == "ARCHIVED.PDF"
        doctor = json.loads(run("--root", str(workspace), "doctor").stdout)
        assert doctor["pdf_count"] == 3
        preserved_timestamp_pdf.unlink()
        removed_pdf = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(workspace), "find", "ARCHIVED"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert removed_pdf.returncode == 1
        assert "No local paper matched" in removed_pdf.stderr
        no_match = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(workspace), "find", "Missing Local Paper"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert no_match.returncode == 1
        assert "Check the copied title or import the PDF first" in no_match.stderr

        index_path = workspace / "references" / "paper_index.jsonl"
        previous_index_time = index_path.stat().st_mtime - 60
        os.utime(index_path, (previous_index_time, previous_index_time))
        rules_path = workspace / "references" / "organization_rules.json"
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        rules["title_overrides"] = {"UPPER.PDF": "Override-Aware Paper"}
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        direct_override = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "find_paper.py"), "Override-Aware Paper", "--root", str(workspace)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert direct_override.returncode == 0
        assert "Override-Aware Paper" in direct_override.stdout
        override_matches = json.loads(run("--root", str(workspace), "find", "Override-Aware Paper", "--json").stdout)
        assert override_matches and override_matches[0]["title"] == "Override-Aware Paper"

        escaped_index = Path(tmp) / "escaped_index.jsonl"
        rejected_output = subprocess.run(
            [
                sys.executable,
                "-B",
                str(INDEX_TOOL),
                "--root",
                str(workspace),
                "--output",
                "../escaped_index.jsonl",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert rejected_output.returncode != 0
        assert "must stay inside workspace root" in rejected_output.stderr
        assert not escaped_index.exists()

        escaped_render = Path(tmp) / "escaped_render.png"
        rejected_render = subprocess.run(
            [
                sys.executable,
                "-B",
                str(TOOL),
                "--root",
                str(workspace),
                "render-page",
                "2501.00001v1",
                "--page",
                "1",
                "--output",
                "../escaped_render.png",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert rejected_render.returncode == 2
        assert "workspace_path_escape" in rejected_render.stderr
        assert not escaped_render.exists()

        symlinked_workspace = Path(tmp) / "symlinked-workspace"
        symlinked_workspace.mkdir()
        external_references = Path(tmp) / "external-references"
        external_references.mkdir()
        (symlinked_workspace / "references").symlink_to(external_references, target_is_directory=True)
        rejected_setup = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(symlinked_workspace), "setup"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert rejected_setup.returncode == 2
        assert "workspace_path_escape" in rejected_setup.stderr
        assert not list(external_references.iterdir())

        rejected_download = subprocess.run(
            [sys.executable, "-B", str(TOOL), "--root", str(workspace), "add", "http://127.0.0.1/private.pdf"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert rejected_download.returncode == 2
        assert "unsafe_download_url" in rejected_download.stderr
        assert not (workspace / "private.pdf").exists()

        assert_pinned_download_boundaries(workspace)

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
        note = organized / "notes" / "reader.html"
        note.write_text(
            '<a href="../download.pdf">Open PDF</a><p>download.pdf must remain prose.</p>\n',
            encoding="utf-8",
        )
        outside_note = Path(tmp) / "outside-note.html"
        outside_note_bytes = b'<a href="../download.pdf">Outside workspace</a>\n'
        outside_note.write_bytes(outside_note_bytes)
        (organized / "notes" / "external.html").symlink_to(outside_note)
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
        updated_note = note.read_text(encoding="utf-8")
        assert 'href="../papers/core/example_text_to_sql_paper.pdf"' in updated_note, updated_note
        assert "download.pdf must remain prose." in updated_note
        assert outside_note.read_bytes() == outside_note_bytes
        organization_manifest = (organized / organization_scope["manifest"]).read_text(encoding="utf-8")
        organization_pack = (organized / organization_scope["reading_pack"]).read_text(encoding="utf-8")
        assert "papers/core/example_text_to_sql_paper.pdf" in organization_manifest
        assert "papers/core/example_text_to_sql_paper.pdf" in organization_pack

        stale = Path(tmp) / "stale-organization"
        run("--root", str(stale), "setup")
        stale_source = stale / "download.pdf"
        stale_source.write_bytes(b"%PDF-1.4\n% stale plan source\n")
        stale_rules = stale / "references" / "organization_rules.json"
        stale_rules.write_text(
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
        stale_plan = organization_items(stale, load_organization_rules(stale))
        stale_target = stale / stale_plan[0]["target"]
        stale_target.parent.mkdir(parents=True, exist_ok=True)
        stale_target.write_bytes(b"%PDF-1.4\n% existing target\n")
        try:
            apply_organization(stale, stale_plan)
        except WorkflowError as exc:
            assert exc.code == "target_conflict"
        else:
            raise AssertionError("expected a stale organization plan to preserve an existing target")
        assert stale_source.exists()
        assert stale_target.read_bytes() == b"%PDF-1.4\n% existing target\n"

        rollback_workspace = Path(tmp) / "rollback-identity"
        run("--root", str(rollback_workspace), "setup")
        first_source = rollback_workspace / "first.pdf"
        second_source = rollback_workspace / "second.pdf"
        first_bytes = b"%PDF-1.4\n% first original\n"
        second_bytes = b"%PDF-1.4\n% second original\n"
        first_source.write_bytes(first_bytes)
        second_source.write_bytes(second_bytes)
        (rollback_workspace / "references" / "organization_rules.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_category": "uncategorized",
                    "categories": [
                        {"name": "core", "keywords": ["text-to-sql"]},
                        {"name": "uncategorized", "keywords": []},
                    ],
                    "title_overrides": {
                        "first.pdf": "First Text-to-SQL Paper",
                        "second.pdf": "Second Text-to-SQL Paper",
                    },
                    "category_overrides": {},
                }
            ),
            encoding="utf-8",
        )
        rollback_plan = organization_items(rollback_workspace, load_organization_rules(rollback_workspace))
        targets = {item["source"]: rollback_workspace / item["target"] for item in rollback_plan}
        first_target = targets["first.pdf"]
        second_target = targets["second.pdf"]
        second_target.parent.mkdir(parents=True, exist_ok=True)
        second_target.write_bytes(b"%PDF-1.4\n% concurrent second target\n")
        original_place = workflow.place_file_without_overwrite

        def replace_first_target(root: Path, source: Path, target: Path) -> tuple[int, int]:
            identity = original_place(root, source, target)
            if target.resolve() == first_target.resolve():
                replacement = rollback_workspace / "concurrent-replacement.pdf"
                replacement.write_bytes(b"%PDF-1.4\n% concurrent first target\n")
                os.replace(replacement, target)
            return identity

        with patch.object(workflow, "place_file_without_overwrite", side_effect=replace_first_target):
            try:
                apply_organization(rollback_workspace, rollback_plan)
            except WorkflowError as exc:
                assert exc.code == "target_conflict"
            else:
                raise AssertionError("expected second target conflict to trigger rollback")
        assert first_source.read_bytes() == first_bytes
        assert second_source.read_bytes() == second_bytes
        assert first_target.read_bytes() == b"%PDF-1.4\n% concurrent first target\n"
        assert second_target.read_bytes() == b"%PDF-1.4\n% concurrent second target\n"

        recovery_workspace = Path(tmp) / "metadata-recovery"
        run("--root", str(recovery_workspace), "setup")
        recovery_source = recovery_workspace / "download.pdf"
        recovery_source.write_bytes(b"%PDF-1.4\n% recovery source\n")
        (recovery_workspace / "references" / "organization_rules.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_category": "uncategorized",
                    "categories": [
                        {"name": "core", "keywords": ["text-to-sql"]},
                        {"name": "uncategorized", "keywords": []},
                    ],
                    "title_overrides": {"download.pdf": "Recovery Text-to-SQL Paper"},
                    "category_overrides": {},
                }
            ),
            encoding="utf-8",
        )
        recovery_plan = organization_items(recovery_workspace, load_organization_rules(recovery_workspace))
        recovery_target = recovery_workspace / recovery_plan[0]["target"]
        with patch.object(workflow, "apply_organization_metadata", side_effect=OSError("injected metadata failure")):
            try:
                apply_organization(recovery_workspace, recovery_plan)
            except WorkflowError as exc:
                assert exc.code == "organization_metadata_pending"
            else:
                raise AssertionError("expected metadata failure to leave a recovery journal")
        journal = recovery_workspace / "references" / "organization_recovery.json"
        assert journal.is_file()
        assert recovery_target.is_file() and not recovery_source.exists()
        recovered = workflow.recover_pending_organization(recovery_workspace)
        assert recovered and recovered["recovered"] == 1
        assert not journal.exists()
        assert json.loads(run("--root", str(recovery_workspace), "find", "Recovery Text-to-SQL Paper", "--json").stdout)[0]["path"] == str(
            recovery_target.relative_to(recovery_workspace)
        )

        interrupted_workspace = Path(tmp) / "interrupted-organization"
        run("--root", str(interrupted_workspace), "setup")
        interrupted_source = interrupted_workspace / "download.pdf"
        interrupted_bytes = b"%PDF-1.4\n% interrupted source\n"
        interrupted_source.write_bytes(interrupted_bytes)
        (interrupted_workspace / "references" / "organization_rules.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_category": "uncategorized",
                    "categories": [
                        {"name": "core", "keywords": ["text-to-sql"]},
                        {"name": "uncategorized", "keywords": []},
                    ],
                    "title_overrides": {"download.pdf": "Interrupted Text-to-SQL Paper"},
                    "category_overrides": {},
                }
            ),
            encoding="utf-8",
        )
        interrupted_plan = organization_items(interrupted_workspace, load_organization_rules(interrupted_workspace))
        interrupted_target = interrupted_workspace / interrupted_plan[0]["target"]
        interrupted_staging = Path(tempfile.mkdtemp(prefix=".literature-workflow-", dir=interrupted_workspace))
        interrupted_temporary = interrupted_staging / "0000.pdf"
        workflow.write_organization_journal(
            interrupted_workspace,
            {"download.pdf": interrupted_plan[0]["target"]},
            [
                {
                    "source": "download.pdf",
                    "target": interrupted_plan[0]["target"],
                    "temporary": str(interrupted_temporary.relative_to(interrupted_workspace)),
                }
            ],
        )
        shutil.move(str(interrupted_source), str(interrupted_temporary))
        interrupted_recovery = workflow.recover_pending_organization(interrupted_workspace)
        assert interrupted_recovery == {"recovered": 0, "restored": 1, "index_entries": 1}
        assert interrupted_source.read_bytes() == interrupted_bytes
        assert not interrupted_target.exists()
        assert not (interrupted_workspace / "references" / "organization_recovery.json").exists()
        assert not interrupted_staging.exists()

        registered_pdf = workspace / "notes" / "attached.PDF"
        registered_pdf.write_bytes(b"%PDF-1.4\n% registered source outside the library folders\n")
        run(
            "--root",
            str(workspace),
            "source",
            "add",
            "--kind",
            "paper",
            "--title",
            "Registered Local PDF",
            "--pdf",
            "notes/attached.PDF",
        )
        registered_matches = json.loads(run("--root", str(workspace), "find", "Registered Local PDF", "--json").stdout)
        assert registered_matches and registered_matches[0]["path"] == "notes/attached.PDF"
        assert json.loads(run("--root", str(workspace), "doctor").stdout)["index_stale"] is False

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
        direct_find = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "find_paper.py"), "ESD", "--root", str(workspace)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert direct_find.returncode == 0
        assert "https://example.com/docs" in direct_find.stdout

    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
