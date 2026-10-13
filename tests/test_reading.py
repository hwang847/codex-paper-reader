"""Regression checks for Unicode lookup, full-page evidence, and inbox filing."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_paper_index as index
import find_paper
import paper_workflow as workflow


def make_pdf(path: Path, pages: list[str], title: str = "Evidence Study") -> None:
    """Write a small valid PDF without a third-party fixture dependency."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Count %d /Kids [%s] >>" % (
            len(pages), " ".join(f"{5 + 2 * i} 0 R" for i in range(len(pages)))
        )).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Title <FEFF" + title.encode("utf-16-be").hex().encode() + b"> >>",
    ]
    for i, text in enumerate(pages):
        page = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
        ) % (6 + 2 * i)
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 14 Tf 50 720 Td ({escaped}) Tj ET".encode()
        objects.extend([page.encode(), f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"])
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend((
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info 4 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode())
    path.write_bytes(data)


class TitleTests(unittest.TestCase):
    def test_cjk_titles_remain_distinct(self):
        titles = ["数据库检索研究", "資料庫檢索研究", "データベースの検索", "데이터베이스 검색"]
        for title in titles:
            with self.subTest(title=title):
                normalized = index.normalize(title)
                self.assertTrue(normalized)
                self.assertEqual(normalized, index.normalize(unicodedata.normalize("NFD", title)))
                self.assertEqual(find_paper.score(title, {"title": title}), 1.0)
                self.assertLess(find_paper.score(title, {"title": "Unrelated English Study"}), 0.45)
                self.assertNotIn(workflow.note_filename(title), {".html", "untitled.html"})
        self.assertNotEqual(index.normalize("ガイド"), index.normalize("カイト"))

    def test_legacy_names_and_aliases(self):
        self.assertEqual(workflow.note_filename("LinkAlign: Scalable Schema Linking"), "linkalign.html")
        self.assertEqual(workflow.note_filename("A Survey of Deep Active Learning"), "a_survey_of_deep_active_learning.html")
        self.assertEqual(index.normalize("Café & SQL"), "cafe and sql")
        self.assertEqual(workflow.normalize("Überblick über Graphen"), "u_berblick_u_ber_graphen")
        old = {"title": "Legacy Paper", "aliases": ["中文标题"], "normalized_aliases": [""]}
        self.assertEqual(find_paper.score("中文标题", old), 1.0)
        self.assertEqual(find_paper.score("Old Name", {"normalized_aliases": ["old_name"]}), 1.0)

    def test_empty_query_cannot_match(self):
        for query in ("", "  ", "---", "?!"):
            self.assertEqual(find_paper.score(query, {"title": "Any Paper"}), 0.0)
        self.assertEqual(workflow.note_filename("?!"), "untitled.html")

    def test_missing_metadata_still_extracts_title(self):
        reader = SimpleNamespace(metadata=None, pages=[SimpleNamespace(
            extract_text=lambda: "Reliable Query Planning\nDepartment of Computing\nAbstract"
        )])
        fake_pypdf = SimpleNamespace(PdfReader=Mock(return_value=reader))
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            self.assertEqual(index.extract_pdf_title(Path("fixture.pdf")), "Reliable Query Planning")

    def test_pymupdf_only_can_index(self):
        doc = MagicMock()
        doc.__enter__.return_value = doc
        doc.metadata = {"title": "中文文献检索"}
        fake_fitz = SimpleNamespace(open=Mock(return_value=doc))
        with patch.dict(sys.modules, {"pypdf": None, "pymupdf": None, "fitz": fake_fitz}):
            self.assertEqual(index.extract_pdf_title(Path("fixture.pdf")), "中文文献检索")
        doc.__exit__.assert_called_once()

    def test_modern_pymupdf_import_takes_precedence(self):
        modern = SimpleNamespace(open=Mock())
        with patch.dict(sys.modules, {"pymupdf": modern, "fitz": None}):
            self.assertIs(index.load_pymupdf(), modern)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.pdf = self.root / "paper.pdf"
        self.pages = ["Abstract\nSummary", "", "Method\n" + "detail " * 3000] + [
            f"Page {i}" for i in range(4, 13)
        ] + ["Experiments\nEvaluation evidence", "Appendix\nImplementation details"]

    def read(self, selection=None):
        with patch.object(workflow, "resolve_pdf", return_value=(self.pdf, {"title": "Paper"})), patch.object(
            workflow, "extract_pdf_pages", return_value=self.pages
        ):
            return workflow.read_pages(self.root, "Paper", selection)

    def test_full_text_keeps_blank_and_late_pages(self):
        result = self.read()
        self.assertEqual(result["page_count"], 14)
        self.assertEqual([p["page"] for p in result["pages"]], list(range(1, 15)))
        self.assertEqual(result["pages"][1]["text"], "")
        self.assertEqual(result["pages"][2]["text"], self.pages[2])
        self.assertIn("Evaluation evidence", result["pages"][12]["text"])
        self.assertIn("Implementation details", result["pages"][13]["text"])
        self.assertTrue(result["warnings"])

    def test_selected_pages_are_physical_sorted_and_unique(self):
        result = self.read("14,3-4,3")
        self.assertEqual([p["page"] for p in result["pages"]], [3, 4, 14])
        self.assertEqual(result["warnings"], [])

    def test_invalid_pages_report_structured_errors(self):
        for selection in ("", "0", "-1", "3-1", "1,", "abc", "1.5", "15", "1-999999999"):
            with self.subTest(selection=selection), self.assertRaises(workflow.WorkflowError) as error:
                self.read(selection)
            self.assertEqual(error.exception.code, "invalid_pages")

    def test_readpack_rejects_nonpositive_page_limit(self):
        with self.assertRaises(workflow.WorkflowError) as error:
            workflow.readpack(self.root, "Paper", 0)
        self.assertEqual(error.exception.code, "invalid_pages")

    def test_poppler_preserves_blank_page_positions(self):
        output = subprocess.CompletedProcess([], 0, "Title\f\fAppendix\f\f", "")
        with patch.object(workflow.shutil, "which", return_value="pdftotext"), patch.object(
            workflow.subprocess, "run", return_value=output
        ):
            pages = workflow.extract_pdf_pages_with_pdftotext(self.pdf, None)
        self.assertEqual(pages, ["Title", "", "Appendix", ""])

    def test_real_pdf_with_available_backends_and_cli(self):
        status = workflow.text_extractor_status()
        if not any(status.values()):
            self.skipTest("no optional PDF text extractor installed")
        make_pdf(self.pdf, [f"Evidence on page {i}" if i != 2 else "" for i in range(1, 15)])
        for backend, available in status.items():
            if not available:
                continue
            with self.subTest(backend=backend):
                extract = getattr(workflow, f"extract_pdf_pages_with_{backend}")
                pages = extract(self.pdf, None)
                self.assertEqual(len(pages), 14)
                self.assertFalse(pages[1].strip())
                self.assertIn("Evidence on page 14", pages[13])
        command = [sys.executable, str(ROOT / "scripts/paper_workflow.py"), "--root", str(self.root)]
        result = subprocess.run(command + ["read", "paper.pdf", "--pages", "2,13-14"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p["page"] for p in json.loads(result.stdout)["pages"]], [2, 13, 14])
        bad = subprocess.run(command + ["read", "paper.pdf", "--pages", "15"], capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("invalid_pages", bad.stderr)

    def test_real_renderers_keep_page_background_opaque(self):
        status = workflow.renderer_status()
        backends = [name for name in ("pymupdf", "pdftoppm", "ghostscript") if status[name]]
        if not backends:
            self.skipTest("no optional PDF renderer installed")
        make_pdf(self.pdf, ["Source evidence", "", "Appendix evidence on page 3"])
        for backend in backends:
            with self.subTest(backend=backend):
                output = self.root / f"{backend}.png"
                getattr(workflow, f"render_page_with_{backend}")(self.pdf, output, 3, 100)
                data = output.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(data[25], 2, "screenshots should be opaque RGB")
                if status["pil"]:
                    from PIL import Image, ImageChops
                    with Image.open(output) as rendered:
                        rgb = rendered.convert("RGB")
                        self.assertEqual(rgb.getpixel((0, 0)), (255, 255, 255))
                        self.assertIsNotNone(ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white")).getbbox())


class InboxTests(unittest.TestCase):
    def test_inbox_filing_preserves_existing_paths_ids_and_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            command = [sys.executable, str(ROOT / "scripts/paper_workflow.py"), "--root", str(root)]
            def run(*args):
                result = subprocess.run(command + list(args), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            (root / "AGENTS.md").write_text("Keep my existing layout.\n", encoding="utf-8")
            run("setup")
            root.joinpath("custom").mkdir()
            root.joinpath("papers/keep").mkdir()
            paths = ["download.pdf", "papers/keep/original.pdf", "custom/registered.pdf"]
            for path in paths:
                make_pdf(root / path, ["Evidence"])
            rules = {
                "version": 1, "default_category": "uncategorized",
                "categories": [{"name": "uncategorized", "keywords": []}],
                "title_overrides": dict(zip(paths, ["多语言文献", "Existing Paper", "Custom Paper"])),
                "category_overrides": {},
            }
            (root / "references/organization_rules.json").write_text(json.dumps(rules), encoding="utf-8")
            records = [
                {"id": "legacy-id", "kind": "paper", "title": "多语言文献",
                 "sources": [{"type": "pdf", "locator": "download.pdf", "role": "primary"}]},
                {"id": "custom-id", "kind": "paper", "title": "Custom Paper",
                 "sources": [{"type": "pdf", "locator": "custom/registered.pdf", "role": "primary"}]},
            ]
            registry = root / "references/source_registry.jsonl"
            registry.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            before = {path: (root / path).read_bytes() for path in paths}
            plan = run("organize", "--inbox")
            self.assertEqual([p["source"] for p in plan["plan"]], ["download.pdf"])
            self.assertTrue((root / "download.pdf").exists())
            self.assertEqual({p["source"] for p in run("organize")["plan"]}, set(paths))
            result = run("organize", "--inbox", "--apply")
            self.assertEqual(result["moved"], 1)
            target = root / plan["plan"][0]["target"]
            self.assertEqual(target.read_bytes(), before["download.pdf"])
            self.assertIn("多语言文献", target.name)
            for path in paths[1:]:
                self.assertEqual((root / path).read_bytes(), before[path])
            updated = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({record["id"] for record in updated}, {"legacy-id", "custom-id"})
            self.assertEqual((root / "AGENTS.md").read_text(encoding="utf-8"), "Keep my existing layout.\n")
            self.assertEqual(run("organize", "--inbox")["plan"], [])


class SourceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.command = [sys.executable, str(ROOT / "scripts/paper_workflow.py"), "--root", str(self.root)]
        self.invoke("setup")
        make_pdf(self.root / "paper.pdf", ["Evidence"])

    def invoke(self, *args, expected=0):
        result = subprocess.run(self.command + list(args), capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def test_different_titles_do_not_merge_and_ids_are_unique(self):
        titles = [
            "ガラスの研究と情報処理システムの設計",
            "カラスの研究と情報処理システムの設計",
            "Model: Efficient Query Planning",
            "Model: Efficient Query Training",
        ]
        for i, title in enumerate(titles):
            pdf = self.root / f"{i}.pdf"
            make_pdf(pdf, ["Evidence"])
            self.invoke("source", "add", "--kind", "paper", "--title", title, "--pdf", pdf.name)
        records = self.invoke("source", "list", "--json")
        self.assertEqual(len(records), 4)
        self.assertEqual(len({r["id"] for r in records}), 4)
        self.assertEqual({r["title"] for r in records}, set(titles))
        error = self.invoke(
            "source", "add", "--kind", "paper", "--title", "Another Study",
            "--id", records[0]["id"], "--pdf", "paper.pdf", expected=2,
        )
        self.assertEqual(error["error"], "entity_id_conflict")
        self.assertEqual(self.invoke("source", "list", "--json"), records)

    def test_fuzzy_link_reuses_existing_entity(self):
        self.invoke("source", "add", "--kind", "paper", "--title",
                    "A Reliable Study of Database Query Planning", "--pdf", "paper.pdf")
        self.invoke("source", "link", "A Reliable Study of Databse Query Planning", "--url", "https://example.org/paper")
        records = self.invoke("source", "list", "--json")
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["sources"]), 2)

    def test_inferred_short_id_cannot_select_another_papers_entity(self):
        make_pdf(self.root / "first.pdf", ["First evidence"], title="Alpha: First Work")
        make_pdf(self.root / "second.pdf", ["Second evidence"], title="Alpha: Second Work")
        rules = {
            "categories": [], "title_overrides": {
                "first.pdf": "Alpha: First Work", "second.pdf": "Alpha: Second Work",
            },
        }
        (self.root / "references/organization_rules.json").write_text(json.dumps(rules), encoding="utf-8")
        first = self.invoke("source", "add", "--kind", "paper", "--title", "Alpha: First Work", "--pdf", "first.pdf")
        second = self.invoke("source", "link", "Alpha: Second Work", "--url", "https://example.org/second")
        self.assertNotEqual(first["id"], second["id"])
        records = self.invoke("source", "list", "--json")
        self.assertEqual(len(records), 2)
        self.assertEqual(next(r for r in records if r["id"] == first["id"]), first)
        self.assertEqual(second["title"], "Alpha: Second Work")
        self.assertIn("https://example.org/second", [s["locator"] for s in second["sources"]])

    def test_legacy_category_and_mixed_language_survey_keys(self):
        title = "Überblick über Graphen 中文"
        legacy = workflow.legacy_title_key(title)[:96].strip("_")
        rules = {"category_overrides": {legacy: "graphs"}}
        self.assertEqual(workflow.category_override(rules, {}, "paper.pdf", title), "graphs")
        directory = self.root / "surveys" / legacy
        directory.mkdir()
        manifest = {
            "version": 1, "kind": "literature_survey", "slug": legacy, "title": title,
            "scope": "Previous scope", "papers": [], "source_documents": [],
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self.invoke("survey", "init", "--title", title, "--scope", "Updated scope", "--paper", "paper.pdf", "--update")
        self.assertEqual(result["manifest"], str(path.relative_to(self.root)))
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(updated["scope"], "Updated scope")
        self.assertEqual(updated["created_at"], manifest["created_at"])
        self.assertFalse((self.root / "surveys" / workflow.survey_slug(title)).exists())

    def test_preview_never_recovers_files_outside_inbox(self):
        custom = self.root / "custom"
        custom.mkdir()
        staging = self.root / ".literature-workflow-test"
        staging.mkdir()
        staged = staging / "0000.pdf"
        make_pdf(staged, ["Interrupted evidence"])
        workflow.write_organization_journal(
            self.root, {"custom/002.pdf": "papers/uncategorized/past.pdf"},
            [{"source": "custom/002.pdf", "target": "papers/uncategorized/past.pdf",
              "temporary": str(staged.relative_to(self.root))}],
        )
        for args in (("organize", "--inbox"), ("organize", "--inbox", "--apply"), ("read", "paper.pdf")):
            self.assertEqual(self.invoke(*args, expected=2)["error"], "organization_recovery_required")
            self.assertTrue(staged.exists())
            self.assertFalse((custom / "002.pdf").exists())
        preview = self.invoke("recover")
        self.assertTrue(preview["pending"])
        self.assertEqual(preview["journal"]["items"][0]["source"], "custom/002.pdf")
        self.assertTrue(staged.exists())
        result = self.invoke("recover", "--apply")
        self.assertEqual(result["restored"], 1)
        self.assertTrue((custom / "002.pdf").exists())
        self.assertTrue((self.root / "paper.pdf").exists())
        self.assertFalse(self.invoke("recover")["pending"])


if __name__ == "__main__":
    unittest.main()
