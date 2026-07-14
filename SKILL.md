---
name: literature-workflow
description: "Use for local literature folders: add/import PDFs, refresh/search indexes, map copied titles to local files, manage multiple sources per paper or technical document, prepare reading packs, render PDF screenshots, and create/update concise HTML notes."
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
Use `organize --apply` when the workspace policy enables automatic filing or the user asks to organize. The command uses local rules, preserves duplicates with collision suffixes, updates local references, and leaves low-confidence items in the configured fallback category. Codex may review or edit the rules when the user's preferred taxonomy changes.

## Folder Contract

- New PDFs can be dropped in the root folder as inbox items.
- Organized PDFs live under `papers/<category>/`; PDFs dropped at the workspace root are inbox items.
- HTML notes go under `notes/`; screenshots go under `notes/assets/`.
- Search index: `references/paper_index.jsonl`.
- Source registry: `references/source_registry.jsonl`.
- Do not apply organization or delete files unless the workspace policy or the user explicitly authorizes it. A dry-run organization plan is always available.

## Source Model

Read targets are entities: `paper`, `tech_doc`, `repo`, `spec`, `dataset`, `slides`, or `unknown`.

Sources point to entities: PDF, arXiv, DOI, URL, GitHub repo, local document, project page, slides, etc. One entity may have many sources. Use the source registry when:

- several sources point to the same paper;
- a copied title refers to a numbered PDF;
- the target is a technical document rather than a paper;
- a project page, repo, or DOI should be associated with an existing PDF.

If a matched entity has no local PDF, explain that and use available local/web source only if permitted by the user and environment.

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
