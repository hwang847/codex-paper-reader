# Changelog

[中文](CHANGELOG.zh-CN.md)

## 2026-07-14

### Survey and Feishu/Lark workflow

- Added scoped survey work packs: selected local papers, optional read-only source drafts, a manifest, and a reading pack under `surveys/`.
- Added safe management of existing survey drafts: they can be registered or explicitly moved without changing their bytes; generated manifests refresh after paper paths change.
- Extended the skill from paper reading to survey synthesis and optional Feishu/Lark handoff through the official `lark-cli`.
- Added guardrails for cloud work: install and authorize only when requested, require an exact destination, preview where supported, and never perform destructive or permission-changing actions by default.

### Reliable paper organization

- Added opt-in PDF organization: detect titles, normalize filenames, assign one category, and preserve duplicate files.
- Added editable workspace rules at `references/organization_rules.json`; new workspaces receive a general starter taxonomy.
- Added `requires_any` and `requires_all` rule gates, so a topic-specific category can require an explicit domain signal before it applies.
- Keep the search index, source registry, BibTeX `Source` comments, and local note links synchronized after files move.
- Reject unsafe category paths and leave ambiguous papers in the fallback category.

### More resilient local PDF handling

- Detect common ACL and conference metadata as non-titles, including multi-line title reconstruction.
- Resolve exact copied titles before fuzzy search and suppress harmless malformed-PDF warnings.
- Render note screenshots with Ghostscript, PyMuPDF, or Poppler `pdftoppm`.

### Documentation and checks

- Rewrote the user quickstart around the normal reader-to-Codex workflow.
- Added coverage for organization, source-path migration, unsafe rules, title extraction, and renderer fallback.
