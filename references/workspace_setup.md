# Workspace Setup

Inspect the chosen folder and existing `AGENTS.md` before changing it. When useful, ask briefly about missing preferences such as reading language, research goal, or automatic filing; reuse known answers rather than imposing a questionnaire. Let the user defer optional choices and explain the defaults used. Without an existing preference or request, leave files in place and cloud services disconnected; optional customization must not block basic reading.

For a new managed library, `setup` creates folders, rules, and indexes without moving PDFs or generating personal instructions. Use `doctor` to check capabilities; help install missing tools in the chosen environment when authorized. No dependency installation, account login, or cloud publishing is an implicit side effect of the Python helpers.

Default layout:

```text
<workspace>/               # new PDFs may arrive here
  papers/<category>/      # optional organized library
  notes/assets/           # HTML notes live in notes/, images in assets/
  references/             # paper_index.jsonl, source_registry.jsonl, organization_rules.json
  surveys/<topic>/        # generated manifests and reading packs
  surveys/sources/        # registered drafts moved here only when requested
```

Preserve an existing layout. The index scans root PDFs, `papers/`, and explicitly registered PDFs elsewhere inside the workspace. Use `source add --pdf` for those files; do not require a move just to read them.

Maintain a short workspace-local `AGENTS.md` with only durable user choices: language, research goal, reading depth, note style, and whether automatic filing is enabled. Merge with existing instructions and retain unrelated imports. Do not copy the skill into it or invent preferences from a one-off request. [The example](../templates/AGENTS.example.md) is a shape reference, not a required template.

Filing runs when the agent invokes the workflow; there is no watcher. The taxonomy in `references/organization_rules.json` is editable. Review title/category uncertainty before applying, and use overrides for corrections. Existing workspaces keep their rules and registry IDs. Run one mutating workflow command at a time; the helpers have conflict recovery, not multi-writer locking.

Close setup with a brief user-facing handoff: what changed, where PDFs and notes belong, which preferences were saved in `AGENTS.md`, verified capabilities and anything still unavailable, and one next reading request. Explain that preferences can be changed through conversation. Report partial readiness honestly rather than claiming untested features are configured.
