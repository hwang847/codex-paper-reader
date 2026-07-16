# Codex Paper Reader Workflow Skill

[中文](README.zh-CN.md) | [Changelog](CHANGELOG.md)

Use this Codex skill beside your usual PDF reader. Keep reading in Zotero, Office, Preview, or a browser; Codex finds the local PDF behind a copied title, explains the paper with you, tracks related sources, writes concise HTML notes, helps you build a scoped survey, and can deposit selected work in Feishu/Lark.

Built and maintained with Codex.

## What You Do

1. Install the skill once.
2. Choose a local folder for your papers.
3. Drop downloaded PDFs there without renaming them.
4. Copy a title from your PDF reader and talk to Codex.

You do not need to make folders, rename numbered downloads, build an index, or edit a registry by hand.

## Quick Start

Requires Python 3.9 or later. Optional PDF text/rendering tools are checked by Codex during setup.

The easiest installation is to give Codex the [repository link](https://github.com/hwang847/codex-paper-reader.git) and say:

```text
Install or update the Codex skill from https://github.com/hwang847/codex-paper-reader.git as literature-workflow. Check for an existing installation first, preserve local changes, validate SKILL.md, and tell me when it is ready.
```

Codex can place and validate the skill for you. If you prefer a terminal, install it manually:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/hwang847/codex-paper-reader.git ~/.codex/skills/literature-workflow
```

`mkdir -p` only ensures that the parent skill directory exists; it is harmless when the directory is already present. An installed skill is normally available on the next Codex turn. If the current task does not detect it, open a new Codex App task or a new CLI session.

Then open your chosen paper folder, or `cd` into it, and say:

```text
Use $literature-workflow to set up this literature workspace.
```

Codex creates the workspace, checks available PDF tools, and writes a compact local `AGENTS.md` from your preferences. Say that you want automatic filing if you want new papers organized automatically.

## Read a Paper

After setup, your everyday loop is simple:

1. Put a new PDF in the workspace root. Names such as `2508.05002v1.pdf`, `2025.findings-naacl.245.pdf`, `download.pdf`, or `Paper.PDF` are all fine.
2. Open it in your normal PDF reader and copy its title.
3. Paste the title into Codex:

```text
Use $literature-workflow. Read this paper with me:
APEX-SQL: Talking to the data via Agentic Exploration for Text-to-SQL
```

Codex refreshes the local index when needed, identifies the corresponding file, starts from the abstract, then explains the thesis and implementable method pipeline. Ask follow-up questions naturally, for example:

```text
Walk me through the pipeline as if I had to implement it.
What state does each agent keep, and how does feedback change the next step?
Relate this paper to the literature review I am writing.
Generate a concise HTML note for this paper.
```

The HTML note reflects the paper and your discussion. Later questions that change the interpretation should update the same note; supported local renderers can add native PDF screenshots.

## Build a Survey

Choose the papers and tell Codex the question and boundary in ordinary language:

```text
Use $literature-workflow. Build a survey scope on execution-feedback training for Text-to-SQL.
Use ExCoT, SQL-Trail, and MTSQL-R1 as the core papers.
Treat my existing integrated_survey.md as read-only source material.
```

Codex creates a small, traceable work pack under `surveys/<topic>/`: a source manifest and a reading pack. It can register your existing survey draft, or move it into `surveys/sources/` when you ask, without changing its contents. Then ask Codex to compare papers, shape the narrative, identify gaps, or write/update survey prose in your chosen style.

## Automatic Rename and Filing

Automatic filing is opt-in: enable it while setting up the workspace, or ask Codex to organize the new PDFs.

When enabled, the workflow:

- detects the real title from PDF text and ignores generic conference metadata when possible;
- renames a download to a normalized paper-title filename;
- places it in one primary `papers/<category>/` folder using editable local rules;
- preserves duplicate files with a suffix instead of overwriting them;
- updates the search index, source registry, BibTeX `Source` comments, and links in local notes when paths change.

The starter categories are deliberately general. Tell Codex how you want your library grouped, and it will adapt `references/organization_rules.json` and your workspace-local `AGENTS.md`. Ambiguous papers stay in the fallback category. The workflow never deletes PDFs.

## Deposit Work in Feishu/Lark

When a note, survey artifact, or sharing path is ready, give Codex the exact Drive-folder or Wiki link and say what to publish:

```text
Use $literature-workflow to publish recommended_readings.md to this Feishu folder: <link>.
```

Codex checks for the official `lark-cli`, explains the exact install before asking permission to install it, guides the one-time authorization, previews the write when supported, and then creates the requested cloud artifact. It will not sync, overwrite, move, delete, or change sharing permissions unless you explicitly ask.

## What Codex Maintains

```text
your-workspace/
├── papers/                 # organized PDFs
├── notes/                  # HTML notes
│   └── assets/             # native PDF screenshots
├── references/             # search index, source registry, filing rules
├── surveys/                # scoped survey manifests, packs, and managed source drafts
└── AGENTS.md               # your durable reading preferences
```

One reading target can have many sources: a local PDF, arXiv, DOI, project page, repository, slides, or technical documentation. Codex records these as one entity, so a copied title does not need to match the downloaded filename.

## Make It Yours

Tell Codex preferences in ordinary language:

```text
Use Chinese for reading and notes.
Focus on implementation details and pipeline reconstruction.
Skip experiments unless I ask.
I am writing a survey, so emphasize related work and positioning.
Track project pages and GitHub repositories with each paper.
```

Codex keeps durable preferences compactly in that workspace's `AGENTS.md`; the public skill supplies the mechanics, while your workspace defines the research context.

## For Maintainers

```bash
python3 tests/smoke_test.py
python3 tests/privacy_scan.py
```
