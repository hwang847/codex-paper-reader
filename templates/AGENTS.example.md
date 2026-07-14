@README.md

# Literature Workspace Rules

- This file is a local example for Codex. Edit it for your own literature folder.
- Users may describe personal preferences in natural language; Codex should infer intent and keep only compact durable rules here.
- Use `$literature-workflow` as the executable workflow.
- Default language is English unless the user asks for another language; record language preference here only when it is stable.
- Workspace root is the current directory containing this `AGENTS.md`.
- This is a paper/document library, not an app; do not start servers or build UI. Do not delete files. Apply organization only when the workspace policy or user explicitly permits it.
- New PDFs belong in the root inbox by default; organized PDFs live under `papers/<category>/`.
- After new files appear, refresh the index; run `organize --apply` only when automatic filing is enabled.
- Treat readable objects as entities: `paper`, `survey`, `tech_doc`, `repo`, `spec`, `dataset`, `slides`, or `unknown`.
- Treat PDF/arXiv/DOI/URL/GitHub/local docs as sources; use `references/source_registry.jsonl` through the workflow for multi-source entities or non-paper documents.
- Use `surveys/<scope>/` for generated survey manifests and reading packs. Existing survey drafts are read-only sources: they may be registered or explicitly moved into `surveys/sources/`, never rewritten.
- Prefer local evidence. Use web only when asked, approved, or needed to download a requested source.
- Reading focus: translate or summarize the abstract first when present, then explain thesis, high-value ideas, method/pipeline, and implementation implications.
- Skip experiments/results unless explicitly asked.
- Avoid reusable prose templates. Headings and note structure should follow the document, the discussion, and the user's current question.
- Mark missing details clearly; label nontrivial interpretation as inference.
- HTML notes require an explicit note trigger, use the workflow filename rule, stay minimal, and should be updated if later discussion changes the understanding.
- For Feishu/Lark, use the official `lark-cli` only when the user asks for cloud work. If it is missing, state the exact install command and obtain explicit approval before installing. Require an exact destination and explicit publication intent; never overwrite, sync, move, delete, or change permissions without separate confirmation.
