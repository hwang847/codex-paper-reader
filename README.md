# Codex Paper Reader Workflow Skill

[中文说明](README.zh-CN.md)

This repository defines a literature-reading workflow and packages it as a Codex skill, so you can use that workflow directly inside Codex.

This repository is developed and maintained with Codex.

It is designed for working with a local paper folder alongside your usual PDF reader. Use it to locate PDFs, map copied paper titles to numbered files, manage related sources, render paper screenshots, discuss method pipelines with Codex, and generate concise HTML notes shaped by your conversation.

This is not a built-in PDF reader. Keep reading PDFs in Zotero, Office, Preview, a browser, or any reader you like. Codex handles the searchable workspace, interactive explanation, source tracking, and notes.

## How It Works

Your part stays small:

- Install the skill once.
- Choose a local folder as your literature workspace.
- Drop PDFs into that folder without renaming them.
- Copy a paper title from your PDF reader and ask Codex to read it with you.
- Tell Codex your preferences when they matter.

Codex can then help you:

- Set up the workspace, index PDFs, and record sources.
- Match copied paper titles to local files such as arXiv IDs, conference IDs, or generic download names.
- Rename PDFs from detected titles and file them into configurable topic folders, while updating local references and preserving duplicates.
- Turn dense papers into explanations that fit your reading style.
- Answer follow-up questions about methods, pipelines, implementation details, related work, or survey positioning.
- Generate concise HTML notes from the paper and your discussion, with screenshots when local PDF rendering is available.

## Workflow Boundary

This skill gives Codex the stable workflow pieces that are repetitive or fragile to redo manually:

- workspace setup and environment checks;
- PDF indexing and copied-title lookup;
- source registry for PDFs, arXiv, DOI, project pages, repos, docs, and slides;
- reading-pack preparation;
- PDF screenshot rendering for notes;
- note filename normalization.

Codex itself handles the flexible parts through conversation:

- explaining the paper in your preferred language and style;
- adapting emphasis, such as method pipelines, implementation details, or related work;
- updating the workspace-local `AGENTS.md` when your preferences become stable;
- applying organization when the workspace policy or your request enables it; Codex can review the rules when your taxonomy changes.

## Quickstart

Install:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/hwang847/codex-paper-reader.git ~/.codex/skills/literature-workflow
```

Restart Codex App or open a new Codex CLI session.

Open the folder you want to use as your literature workspace, or `cd` into it, then tell Codex:

```text
Use $literature-workflow to set up this literature workspace.
```

Codex will create the workspace structure, initialize indexes, check local capabilities, and maintain a compact `AGENTS.md` for your preferences. You do not need to prepare folders or Python packages by hand. If you want automatic filing, say so while setting up the workspace; Codex will use local organization rules and keep ambiguous items in a fallback folder.

Then drop PDFs into the workspace and talk naturally:

```text
Refresh the index.
Read this paper with me.
Explain the method pipeline.
Generate an HTML note.
```

## Everyday Use

You do not need to rename downloaded PDFs. Files named like `2508.05002v1.pdf`, `2025.findings-naacl.245.pdf`, or `download.pdf` are fine.

After the workspace is set up:

1. Put new PDFs in the workspace root as inbox items, or directly under `papers/`.
2. Open the paper in your PDF reader.
3. Copy the paper title.
4. Tell Codex:

```text
Use $literature-workflow. Read this paper with me:
APEX-SQL: Talking to the data via Agentic Exploration for Text-to-SQL
```

Codex will refresh the index when needed, optionally rename and categorize the new PDF, match the copied title to the local file, prepare a reading pack, and start an interactive reading session. You can ask follow-up questions about the method, pipeline, implementation details, related work, or any part you care about.

When you are ready, ask Codex to generate an HTML note. The note is based on the paper plus your discussion, so it should reflect your focus instead of becoming a generic summary.

## Workspace

```text
your-workspace/
├── papers/                 # categorized PDFs, such as papers/methods/
├── notes/                  # HTML notes
│   └── assets/             # screenshots
├── references/             # index and source registry
└── AGENTS.md               # local Codex preferences
```

New PDFs can stay in the workspace root as inbox items. When organization is enabled, Codex moves them to `papers/<category>/` and normalizes the filename from the paper title. The rules are editable at `references/organization_rules.json`.

The filing scheme is a local preference, not a fixed taxonomy. Tell Codex how you want papers grouped, and it can update the rules and workspace `AGENTS.md`.

## Customize

Tell Codex what you care about:

```text
My notes should focus on implementation details and pipeline reconstruction.
Prefer concise HTML notes.
Skip experiments unless I ask.
Use Chinese for reading and notes.
I am writing a literature review, so focus more on related work and positioning.
Track project pages and GitHub repos as sources.
```

Codex will turn stable preferences into local `AGENTS.md` rules and update them as your workflow changes.

## Sources

A read target is an entity: `paper`, `tech_doc`, `repo`, `spec`, `dataset`, `slides`, or `unknown`.

A source points to an entity: PDF, arXiv, DOI, URL, GitHub repo, local document, project page, slides, etc.

One entity can have multiple sources. For example, a paper may have a local PDF, arXiv URL, DOI, project page, and GitHub repo.

## For Maintainers

Run tests from this repository root:

```bash
python3 tests/smoke_test.py
python3 tests/privacy_scan.py
```
