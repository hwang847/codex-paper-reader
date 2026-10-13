# 📚 Codex Paper Reader

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**Your local paper library, ready for a conversation with Codex.**

A lightweight Codex skill for **managing and reading literature in a local workspace**. Find PDFs by copied title, explore methods and evidence, and turn your discussions into personalized HTML notes. Keep Zotero or your preferred PDF reader open alongside Codex; bring the resulting sources and notes into your next writing or presentation task.

📂 Collect → 🔎 Find → 💬 Discuss → 📝 Keep notes → 📽️ Share your understanding

Built and maintained with Codex.

## 🚀 Start with a Conversation

**1. 📦 Install the skill**

```text
Install this skill for me: https://github.com/hwang847/codex-paper-reader.git
```

**2. 📂 Open your paper folder in Codex**

```text
Use $literature-workflow to prepare this folder for reading papers.
```

Codex checks the environment, helps set up Python and PDF tools as needed, and asks about relevant reading or filing preferences. It preserves your existing files and records agreed preferences in a local `AGENTS.md`. After setup, it explains file locations, ready-to-use capabilities, and any remaining steps.

**3. 💬 Drop in a PDF and copy its title from your reader**

Place new PDFs in the workspace root. Download names such as `2508.05002v1.pdf` work as they are:

```text
Read this paper with me: <copied title>
Walk me through its key idea and method as if I were implementing it.
Now make an HTML note based on our discussion.
```

Codex uses the title index to locate the PDF and refreshes the index when the library changes. For scans or ambiguous titles, a file path or title correction helps resolve the source.

## 🔬 From a Folder of PDFs to a Working Library

| Capability | What you get |
| --- | --- |
| 🔎 Find by title | Match copied titles, aliases, arXiv IDs, or filenames to local PDFs. |
| 🗂️ Organize papers | Preview title-based filenames and category folders; apply filing on request or through your saved preference. |
| 🔗 Connect sources | Associate PDF, arXiv, DOI, code, and technical documentation with one reading target. |
| 💬 Read for your goal | Discuss the contribution, pipeline, implementation, experiments, or writing choices at your preferred depth. |
| 📝 Keep what matters | Request concise HTML notes with source links and PDF figure screenshots; refine the same note as the discussion develops. |
| 📑 Compare a selected corpus | Define a review question and source set, compare evidence, and draft a synthesis with Codex. |

### 🧩 How It Works

- **Local title index.** Python helpers combine available BibTeX records, PDF metadata, and first-page text into `references/paper_index.jsonl`. Normalized titles and aliases support exact and fuzzy matching; lookup refreshes stale records.
- **Source continuity.** `references/source_registry.jsonl` links multiple sources to an entity. Filing updates managed source paths, BibTeX source comments, note links, and generated survey references.
- **Reviewable organization.** Editable keyword rules and explicit overrides propose categories. A preview precedes file moves, and collision suffixes preserve same-name PDFs.
- **Evidence for discussion.** Page-level text and native PDF screenshots give Codex material to inspect and cite. The scripts handle repeatable file operations; Codex handles interpretation and writing.

The [command reference](references/commands.md) covers these helpers. Your reader displays the paper; Codex helps you work through it.

## 🛠️ Continue Creating in Codex

**The library is the starting point. Your sources, notes, and discussion can become inputs to the next task.**

| Next step | Try asking Codex |
| --- | --- |
| ✍️ Polish research notes | “Edit this note for clarity, keeping my judgments and source links.” |
| 📄 Write or revise documents | “Turn these notes into a related-work draft,” or “Revise this report for a technical audience.” |
| 📽️ Prepare a presentation | “Use these papers and notes to build a group-meeting deck with figures, citations, and speaker notes.” |

These follow-on tasks use Codex's writing abilities and, where needed, available document or presentation skills, plugins, and tools in the [Codex ecosystem](https://developers.openai.com/plugins). This project supplies the literature workflow and reusable local materials; file-format editing and export depend on the tools in your environment. Ask Codex to help choose and configure them for the output you need.

## 🎯 Make It Yours

```text
I am writing a survey. Focus on how each paper relates to prior work.
When reading for paper writing, include evaluation design and relevant appendices.
Remember these preferences in this workspace's AGENTS.md.
```

Language, reading depth, note style, categories, and follow-on workflows can evolve through conversation. Codex maintains your local preferences; the shared skill stays reusable across projects.

Existing libraries can keep their layout. A new workspace normally uses `papers/`, `notes/` (figures in `notes/assets/`), `references/`, and `surveys/`. Filing runs when Codex invokes the workflow, with your local files as the primary copy.

## 🔌 Extend to Your Work Tools

Connect a service when you have a use for it. Feishu/Lark is one example:

```text
Help me connect this workspace to Feishu for archiving selected notes.
Find a suitable CLI on GitHub, help me install it, and keep the setup in this project.
```

Codex verifies the tool's source and compatibility, assists with authorized installation and login, and records usage in the workspace's `connectors/README.md` or existing setup notes. You choose the artifacts and destination for each publishing task. Other services follow the same approach, using the tools available for them.

## ⚙️ Environment and Installation

- **Host:** standard `SKILL.md` packaging, primarily for Codex. Other skill-capable agents can reuse it with local file and command access; setup depends on the host.
- **Local helpers:** Python 3.9+, with text extraction and rendering supplied by tools such as PyMuPDF or Poppler. Codex can help set these up on demand.
- **File organization:** POSIX file-moving APIs, for macOS/Linux or Windows through WSL. Current validation runs on macOS.

<details>
<summary>📦 Manual installation or updating an existing copy</summary>

For a fresh installation:

```sh
mkdir -p ~/.agents/skills
git clone https://github.com/hwang847/codex-paper-reader.git ~/.agents/skills/literature-workflow
```

Already installed under `~/.codex/skills` or another supported location? Ask Codex to update that copy while preserving your changes. If discovery needs a refresh, restart the Codex session. See [Codex skill setup](https://learn.chatgpt.com/docs/build-skills) for host-specific guidance.

</details>

[🗒️ Changes](CHANGELOG.md) · [🛠️ Customize or contribute](CONTRIBUTING.md) · [📜 License](LICENSE)
