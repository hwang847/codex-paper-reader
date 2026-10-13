# Changelog

[中文](CHANGELOG.zh-CN.md)

## 2026-10-13: Local Library, Broader Creative Workflow

- Reworked all five READMEs around local literature management and reading, with a three-step quickstart and clearer visual navigation.
- Explained title indexing, multi-source records, previewed filing, and page-level evidence using the existing implementation.
- Added optional paths from notes to polished writing, documents, and presentations through available Codex ecosystem tools; kept work connectors as extensions.
- Documentation-only update; skill behavior, command interfaces, and workspace formats are unchanged.

## 2026-10-13: Optional Work Connectors

- Kept reading, sources, notes, and surveys as the core; moved Feishu/Lark to an example of optional work connectors in all five READMEs.
- Replaced the provider-specific guide with on-demand GitHub CLI discovery, authorized installation, and workspace-local setup records. No new runtime, automatic installation, or cloud connection.
- Preserved scoped publishing and credential boundaries while leaving tool choice and customization with the host agent.

## 2026-10-13: Leaner Literature Workflow

- Reduced the always-loaded skill to task boundaries, evidence handling, and source continuity. Setup, commands, surveys, and Feishu publishing are on-demand references.
- Rewrote the quickstart around installation by conversation, an existing paper folder, and copied titles. Added traditional Chinese, Japanese, and Korean alongside English and simplified Chinese.
- First-time setup can ask brief, relevant preference questions and ends with a clear summary of saved choices, file locations, verified capabilities, and the next reading step.
- Kept reading depth and output structure with the host agent and workspace preferences; experiments and appendices are available for writing and critical reading.
- Added `read [--pages 1,3-5]` for untruncated page text with physical PDF page numbers. `readpack` remains a preview.
- Added `organize --inbox` to restrict filing to newly dropped root PDFs without reorganizing existing folders.
- Made interrupted filing recovery explicit with `recover [--apply]`; previews and reads no longer trigger hidden file moves.
- Prevented fuzzy source-title matching from merging distinct entities; retained legacy category keys and survey directories.
- Fixed multilingual title matching and filenames, blank-page loss in Poppler extraction, and title indexing with PyMuPDF or missing PDF metadata.
- Use the current PyMuPDF import name with a legacy fallback, preventing deprecation messages from corrupting CLI JSON.
- Render page screenshots with opaque backgrounds so source text stays visible in dark note viewers.
- Preserved existing commands and workspace formats. No automatic library migration, new service, model dependency, or cloud connection.
- Added focused regression coverage and repaired release privacy scanning for untracked files and reachable history.

## 2026-07-16

### Easier installation and standards review

- Added a Codex-first installation path: users can give Codex the GitHub repository link and ask it to install or update the skill safely.
- Kept the manual `git clone` path as an explicit fallback and clarified when a newly installed skill becomes available.
- Revalidated the package against the Codex Skill structure, metadata, progressive-disclosure, smoke-test, syntax, and privacy requirements.

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

### Security hardening

- Keep every generated index, survey artifact, note screenshot, and organization target inside the workspace; reject traversal and external symlink escapes.
- Restrict path migration to generated survey metadata and actual HTML link attributes, preserving user prose and registered source documents.
- Harden remote PDF imports: public HTTP(S) hosts only, redirects blocked, 100 MiB streaming limit, temporary-file validation, and atomic final placement.
- Require explicit approval before installing a missing Feishu/Lark CLI; added regression coverage for the new boundaries.
