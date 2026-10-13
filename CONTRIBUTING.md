# Customize or Contribute

The shared skill defines evidence and file-handling contracts, not a research script. Keep decisions with the host agent unless code makes an operation measurably more reliable.

## Choose the Smallest Change

- Personal preferences: ask your agent to maintain the literature workspace's `AGENTS.md`.
- Categories and title corrections: edit workspace `references/organization_rules.json`.
- A reusable specialist workflow: add a focused reference linked from `SKILL.md`.
- A repeatable file operation: extend the existing Python CLI and add a behavior test.
- A new external service: follow [work connectors](references/work_connectors.md); let the host choose a CLI and keep setup records in the user's workspace. Add shared code only for a demonstrated reusable need.

No plugin framework or model-specific wrapper is required. Do not store personal paths, credentials, source PDFs, or private research notes in this repository.

## Compatibility Contract

Keep the skill name `literature-workflow`, existing commands, entity IDs, registry schemas, and default filename conventions stable. New options should be additive. Preserve existing workspace instructions, filing rules, and read-only source drafts. Never silently migrate a library, replace a user's note, or broaden a publishing request.

`scripts/build_paper_index.py` owns indexing and title normalization; `find_paper.py` ranks candidates; `paper_workflow.py` handles page reads, source records, filing, surveys, and figures. These are local helpers, not an agent runtime. Mutating commands assume one writer per workspace.

English `README.md` is the canonical introduction. Keep simplified Chinese, traditional Chinese, Japanese, and Korean quickstarts consistent with it. Put agent-only details in `SKILL.md` or its references.

## Check Before Sharing

From the skill repository, using Python 3.9+:

```sh
python3 tests/smoke_test.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/privacy_scan.py
```

The standard-library tests cover CLI behavior, source integrity, path boundaries, download safety, and multilingual/page-reading regressions. For a PDF backend change, also exercise a real multi-page PDF with that backend and inspect a rendered page. Optional dependency tests may skip when a backend is unavailable; report that limitation.

Current validation runs on macOS. File-moving helpers require POSIX directory-descriptor operations; native Windows is not supported. Linux/WSL and other host agents need their own integration checks. Do not claim cross-platform validation from Python syntax checks alone.

Validate skill metadata using the host's skill validator when available. Review the diff, translated instructions, local links, and source-to-output behavior before release. Privacy scanning is a heuristic check of working files and reachable Git history, not a security guarantee.
