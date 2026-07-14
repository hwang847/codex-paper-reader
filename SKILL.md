---
name: literature-workflow
description: "Use for local literature workspaces: organize and read papers, map copied titles to local PDFs, manage paper and survey sources, prepare scoped survey work packs, create concise HTML notes, and hand off selected research artifacts to Feishu/Lark."
---

# Literature Workflow

Use this skill when a user wants Codex to set up a base literature workflow, then evolve the workspace through local preferences in `AGENTS.md`.

## Script

Resolve relative paths from this skill directory. Main script:

```text
scripts/paper_workflow.py
```

Run against the current literature folder:

```text
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" setup
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" doctor
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" add <path|arxiv_id|url>
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" refresh
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" organize --apply
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" find "<title|alias|arxiv_id>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" readpack "<title|alias|path>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" render-page "<title|alias|path>" --page <n> --output <png> --dpi auto
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" note-name "<paper title>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" survey init --title "<survey title>" --scope "<question and boundary>" --paper "<paper>" --paper "<paper>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" survey refresh "<survey title>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" survey source add <draft.md> --move
```

Source registry:

```text
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" source init
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" source list
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" source add --kind tech_doc --title "<title>" --url "<url>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" source link "<entity query>" --url "<url>" --repo "<github-url>"
python3 <skill-dir>/scripts/paper_workflow.py --root "$PWD" source show "<entity query>"
```

Text extraction needs one of `pypdf`, PyMuPDF, or system `pdftotext`. Screenshots need Ghostscript, PyMuPDF, or Poppler `pdftoppm`; Pillow is needed only for cropping.

## Workspace Setup

When the user asks to set up, initialize, or configure a literature workspace:

1. Run `setup` for the target workspace.
2. Run `doctor` to inspect text extraction and rendering capabilities.
3. Read `references/workspace_setup.md`.
4. Use the user's stated preferences and the current conversation to create or update the workspace-local `AGENTS.md`.
5. Keep `AGENTS.md` personalized and compact; do not blindly copy a template.
6. If optional dependencies are missing, explain their impact briefly and offer to install or proceed without that feature.
7. When future conversation reveals stable preference changes, maintain `AGENTS.md` so it stays current.

This skill provides a base workflow, not a final universal policy. Let the user's local `AGENTS.md` evolve through conversation.
Use `organize --apply` when the workspace policy enables automatic filing or the user asks to organize. The command uses local rules, preserves duplicates with collision suffixes, updates local references, and leaves low-confidence items in the configured fallback category. Categories can use `requires_any` or `requires_all` to limit a topic-specific rule to matching documents. Codex may review or edit the rules when the user's preferred taxonomy changes.

## Folder Contract

- New PDFs can be dropped in the root folder as inbox items.
- Organized PDFs live under `papers/<category>/`; PDFs dropped at the workspace root are inbox items.
- HTML notes go under `notes/`; screenshots go under `notes/assets/`.
- Survey manifests and reading packs go under `surveys/<scope>/`; managed source drafts can live in `surveys/sources/`.
- Search index: `references/paper_index.jsonl`.
- Source registry: `references/source_registry.jsonl`.
- Do not apply organization or delete files unless the workspace policy or the user explicitly authorizes it. A dry-run organization plan is always available.

## Source Model

Read targets are entities: `paper`, `survey`, `tech_doc`, `repo`, `spec`, `dataset`, `slides`, or `unknown`.

Sources point to entities: PDF, arXiv, DOI, URL, GitHub repo, local document, project page, slides, etc. One entity may have many sources. Use the source registry when:

- several sources point to the same paper;
- a copied title refers to a numbered PDF;
- the target is a technical document rather than a paper;
- a project page, repo, or DOI should be associated with an existing PDF.

If a matched entity has no local PDF, explain that and use available local/web source only if permitted by the user and environment.

## Survey Pipeline

Use `survey` when the user wants to write, map, compare, or maintain a literature review based on several selected papers.

1. Establish the question, boundary, intended audience, and selected papers; ask at most one focused question when needed.
2. Run `survey init` with the exact scope and each selected paper. Add an existing survey draft with `--source`; it is registered as read-only.
3. Use the generated `manifest.json` and `reading_pack.md` to read the scoped papers and trace claims back to local sources. Do the synthesis in the user's requested style; do not emit a generic survey template.
4. Existing source drafts may be moved with `survey source add <path> --move`, but their bytes must never be rewritten. Generated scope files are the only survey files the script changes.
5. Run `survey refresh` after paper or source paths change. It preserves the scope while reporting unavailable sources.

Read `references/survey_workflow.md` before designing a nontrivial survey, comparison table, or survey update.

## Feishu/Lark Handoff

Use this only when the user explicitly asks to deposit, publish, sync, or manage research artifacts in Feishu/Lark.

1. Check `lark-cli`. If it is missing, install the official CLI with `npx @larksuite/cli@latest install`; do not ask the user to install it manually.
2. Before any Lark command, read the version-matched official `lark-cli skills read lark-shared` and the relevant `lark-doc`, `lark-drive`, `lark-markdown`, or `lark-wiki` guide.
3. Help configure and authenticate only when required. Never expose secrets, preserve opaque authorization URLs exactly, and use the official device flow.
4. Require a concrete Drive folder URL/token or Wiki URL/token and explicit publication intent before writing. Preview with `--dry-run` where available; do not overwrite, move, sync, delete, or change permissions without a separate confirmation.
5. Prefer native Markdown for Markdown research artifacts, Drive upload for attachments/PDFs, and Docs only when the user requests a cloud document.

Read `references/lark_handoff.md` before a Feishu/Lark action.

## Reading Pipeline

1. If new files were copied in, run `refresh`, then `organize --apply` when automatic filing is enabled.
2. Run `readpack` for papers with PDFs; use `source show` for non-PDF or multi-source entities.
   `readpack` may identify method-like sections as `method`, `workflow`, or `system`; use `method_heading`, `method_label`, and `section_candidates` before doing any manual PDF text scan.
3. Start by translating or summarizing the abstract in the user's language when an abstract exists; use adaptive wording, not a fixed heading.
4. Explain the thesis, high-value ideas, and why it matters for the user's research context.
5. Explain the method/workflow as an implementable pipeline: inputs, outputs, modules, state, data structures, control flow, prompts/tools/retrieval/training/inference/verification/failure handling.
6. Add an end-to-end example or pseudocode/interfaces only when useful.
7. Skip experiments/results unless the user explicitly asks, except for minimal claims needed to explain motivation or contribution.

If the work is adjacent to, rather than central to, the user's research focus, explain that relation instead of forcing a domain-specific framing.

## HTML Notes

Create or update HTML only after an explicit note trigger such as "generate an HTML note", "write notes", "生成笔记", "整理笔记", or "写成 HTML".

Use the discussion history and the user's perspective. Keep HTML standalone, browser-openable, and minimal. Generate the filename with `note-name`.

Headings must be paper-specific and adaptive; never mechanically reuse labels like "摘要直译", "我们关心的关键点", or "高价值创新".

For a pipeline or architecture image, use native `render-page` output. Cropping is allowed for layout, but do not edit, replace, annotate, rewrite, or otherwise alter screenshot content unless explicitly asked. If no renderer is available, omit the image and briefly record the reason in the note.

If later discussion changes the understanding of the same entity, update the existing HTML.
