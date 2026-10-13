# Local Helpers

Commands below are arguments to `python3 <skill-dir>/scripts/paper_workflow.py --root <workspace>`. Quote paths and titles containing spaces. Use command `--help` for options. The helpers have no model API, cloud publishing, or background process; `add` can download a requested public PDF.

| Need | Command | Result |
| --- | --- | --- |
| Initialize a library | `setup` | Create missing folders/metadata; preserve existing preferences |
| Check dependencies | `doctor` | Available extractors/renderers and index status |
| Find by copied title/ID | `find "<query>" --json` | Ranked candidates; refresh stale index automatically |
| Read exact evidence | `read "<query or path>" --pages 1,3-5` | JSON with physical PDF page numbers and full page text |
| Read the whole PDF | `read "<query or path>"` | All pages, including experiments and appendices |
| Get a quick preview | `readpack "<query or path>"` | Heuristic abstract/method snippets; default first 12 pages |
| Render a figure page | `render-page "<query>" --page 3 --dpi auto` | PNG in `notes/assets/`; optional `--crop left,top,right,bottom` |
| Choose a note filename | `note-name "<title>"` | Lowercase title or short prefix, separated by underscores |
| Rebuild index | `refresh` | `references/paper_index.jsonl` |
| Import a PDF | `add <path or arxiv_id or URL>` | Copy/download to root inbox; refresh index |
| Preview new-PDF filing | `organize --inbox` | Title-based paths and category decisions for root PDFs |
| Apply new-PDF filing | `organize --inbox --apply` | Collision-safe moves and managed-reference updates |
| Inspect an interrupted filing | `recover` | Pending source/target paths; no recovery side effects |
| Finish authorized recovery | `recover --apply` | Restore staged files or reconcile completed moves |

`read` page numbers start at 1 and refer to PDF positions, not printed page labels. Empty text can indicate a blank, scanned, or image-only page; use rendering/OCR as needed. `readpack` omits and truncates content by design and is not a substitute for reading evidence. Extracted PDF text can scramble columns, equations, and tables.

Text extraction needs one of `pypdf`, PyMuPDF, or Poppler `pdftotext`. Rendering needs PyMuPDF, Ghostscript, or Poppler `pdftoppm`; cropping needs Pillow. A minimal Python-only option is PyMuPDF, with Pillow for crops. `doctor` does not install anything. Shell examples assume `python3`; use the actual interpreter on the host.

## Entities and Sources

One readable entity may have multiple sources. For example:

```text
source add --kind paper --title "Paper Title" --pdf papers/download.pdf --alias "Short Name"
source link "Paper Title" --arxiv 2601.01234 --repo https://github.com/example/project
source add --kind tech_doc --title "Tool Manual" --doc docs/manual.md
source show "Paper Title"
source list
```

Registry: `references/source_registry.jsonl`. A local source must stay in the workspace; use `add` to copy an external PDF first. Source registration stores metadata and does not fetch a linked URL. IDs and source locators survive filing; notes and survey metadata retain their links. For an ambiguous match, select a verified path instead of choosing the highest score blindly.

## Filing Rules

Edit `references/organization_rules.json`, preserving its schema: categories have `name` and `keywords`, with optional `requires_any` / `requires_all` gates. `title_overrides` and `category_overrides` correct decisions by title/path/filename. The keyword classifier is a starting point; agent judgment belongs in reviewed rules, not invented confidence claims. Unmatched items use `default_category`.

Without `--inbox`, `organize` considers the entire indexed library, including registered custom folders. Preview before applying that wider scope. Filing preserves PDFs with collision suffixes, updates the source registry, BibTeX `Source` comments, HTML link attributes, and generated survey paths. It cannot rewrite arbitrary paths in other applications.

A pending organization blocks further library operations instead of silently moving files. Inspect `recover` and finish with `recover --apply` only within the authorized scope; recovery can involve paths outside today's inbox. `doctor` and `note-name` remain available. Do not remove the journal manually.

Remote `add` accepts public HTTP(S) PDF URLs, blocks redirects/private hosts, and limits downloads to 100 MiB. For landing pages, resolve the actual PDF using the host's available tools or ask for a local file; do not bypass access controls.
