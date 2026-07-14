# Workspace Setup Guidance

Use this reference only when the user asks to set up, initialize, or configure a literature workspace.

## Principle

Let scripts handle mechanical setup. Let Codex handle personalization.

Run `scripts/paper_workflow.py --root <workspace> setup` to create the standard folders, organization rules, source registry, and index. Run `doctor` after that. Then create, update, and maintain the workspace's local `AGENTS.md` from the user's intent.

This open-source skill provides base mechanics and a starting workflow. The user's own `AGENTS.md` is the evolving local workflow.

Keep scripts for capabilities that are deterministic, repetitive, or fragile when done manually: indexing, title-to-PDF lookup, source registry updates, PDF rendering, note filenames, environment checks, and policy-controlled organization. The scripts make filing collision-safe and keep references synchronized; Codex decides the user's taxonomy and when that policy should apply.

Do not treat `templates/AGENTS.example.md` as a fixed file to copy. It is only a shape reference.

Do not ask the user to create `papers/`, `notes/`, `notes/assets/`, or `references/`; setup creates them. Do not ask the user to inspect Python packages; use `doctor` and handle missing optional dependencies.

## Interaction

If the user gives enough preference context, act immediately. If the workspace preference is unclear, ask one short question at most, such as:

```text
What should Codex optimize for in this literature folder: fast paper reading, implementation-focused notes, survey mapping, or something else?
```

Good preference signals include:

- language;
- research area;
- how much to emphasize method pipelines;
- whether to skip experiments by default;
- HTML note style;
- naming rules;
- source-management needs;
- topics or actions to avoid.

## AGENTS.md

Generate `AGENTS.md` as a compact local contract for Codex. It should usually include:

- imports, if the user's local environment has stable private imports;
- workspace purpose;
- folder rules;
- source/entity rules;
- reading priorities;
- note-generation rules;
- explicit constraints from the user.

Keep it short. Remove motivational prose, examples that only belong in README, and anything the skill already covers.

If `AGENTS.md` already exists, read it first and update it conservatively. Preserve stable user preferences. Do not overwrite unrelated local runtime imports. When the user later changes a durable preference, update `AGENTS.md` again instead of leaving the workspace rules stale.
