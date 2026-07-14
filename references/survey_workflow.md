# Survey Workflow

Use this reference when a request spans several papers or an existing survey draft.

## Scope First

Record four things before drafting: the research question, inclusion boundary, selected paper entities, and audience. A `survey init` manifest is a reproducible source list, not a substitute for judgment or prose.

## Sources and Drafts

- Resolve every selected paper locally before relying on it.
- Treat existing Markdown, text, HTML, or DOCX drafts as read-only source documents. The workflow may register or move them, never rewrite their bytes.
- Use `survey source add <path> --move` only when the user asks to manage the source document under `surveys/sources/`.
- Run `survey refresh` after paper organization or source moves; report missing items rather than silently dropping them.

## Synthesis

Follow the user’s requested narrative rather than a fixed structure. Keep evidence distinct from interpretation, compare methods on the axes that matter to the question, and call out disagreements, boundary conditions, and unresolved gaps. Cite the local entity title or source when making a claim.

Only create or rewrite actual survey prose when the user explicitly asks. The generated `manifest.json` and `reading_pack.md` are safe to update; an existing user draft is not.
