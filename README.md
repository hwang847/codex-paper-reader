# Codex Paper Reader

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**Read papers with an agent. Keep the understanding, not just the PDF.**

A lightweight skill for discussing papers, managing sources, writing personalized HTML notes, and building literature reviews. Use it alongside Zotero, your browser, or any PDF reader. Built and maintained with Codex.

## 🚀 Quick Start

**1. Ask Codex to install it**

```text
Install this skill for me: https://github.com/hwang847/codex-paper-reader.git
```

**2. Open your paper folder in Codex**

Choose any local folder, then say:

```text
Use $literature-workflow to prepare this folder for reading papers.
```

Codex checks the environment and may ask a few short questions about your reading goals, language, or filing preferences. It preserves existing files and instructions, and records agreed preferences in a local `AGENTS.md`. After setup, it explains where your files belong, what is ready, anything still missing, and how to start reading. Python and PDF tools can also be set up with Codex's help; no advance configuration is needed. You can adjust your preferences later through conversation.

**3. Drop in a PDF and start talking**

Keep download names such as `2508.05002v1.pdf`. Copy the paper title from your reader:

```text
Read this paper with me: <copied title>
Walk me through the method as if I were implementing it.
Now make an HTML note based on our discussion.
```

Codex finds the corresponding local PDF through the title index. You do not need to rename files or maintain the index yourself. Scans, unusual layouts, or ambiguous titles may need a path or title correction.

## ✨ What It Helps With

| You ask | Codex and the skill help you |
| --- | --- |
| “Explain this in my research context.” | Read, translate, and discuss at your preferred depth, including experiments and appendices when relevant. |
| “Keep the points we worked out.” | Create concise, paper-specific HTML notes with source links and PDF figure screenshots; update the same note as your understanding changes. |
| “Organize these new papers.” | Preview title-based renaming and category folders, then file PDFs without overwriting duplicates or breaking managed links. |
| “This code repository belongs to that paper.” | Connect PDF, arXiv, DOI, code, and documentation as sources of one reading target. |
| “Compare these papers for my review.” | Maintain a selected source set, compare evidence, and draft a synthesis when asked. |

Notes are created when requested, not after every answer. Filing is opt-in and runs when Codex invokes the workflow, not through a background watcher. Your local files remain the primary copy.

## 🎯 Make It Yours

Tell Codex what you need:

```text
I am writing a survey. Focus on how each paper positions itself against prior work.
When we read for paper writing, include evaluation design and relevant appendices.
Remember these preferences in this workspace's AGENTS.md.
```

You can also customize languages, note styles, categories, and your reading workflow through conversation. Existing libraries need not adopt a new folder layout.

New managed workspaces normally use `papers/`, `notes/` (images in `notes/assets/`), `references/`, and `surveys/`. Drop new PDFs in the workspace root; ask Codex to file them or enable that preference.

## 🔌 Optional Work Connectors

Want to use your research in another service? Tell Codex what you need, for example:

```text
Help me connect this workspace to Feishu for archiving selected notes.
Find a suitable CLI on GitHub, help me install it, and keep the setup in this project.
```

Codex checks the tool's source and compatibility, helps with authorized installation and login, and records how to use it in the workspace's `connectors/README.md` (or your existing setup notes). Feishu/Lark is just one example; other services depend on available tools. Nothing is preinstalled or automatically synced, and a connection is not required for reading or notes.

## Scope and Compatibility

The skill provides a small workflow and reliable local helpers. **The host agent does the reasoning and writing.** This is not a PDF reader, an unattended research service, or a general-purpose chat bot. Bring your usual reader and choose the sources you want to study; no model API key or dedicated server is required by the skill.

The package uses standard `SKILL.md` instructions with optional Python 3.9+ helpers. Codex is the primary target. Other skill-capable agents may reuse it if they support local files and command execution; installation and tool access depend on the host. PDF extraction/rendering needs optional tools that Codex can help install when needed.

Safe file-moving helpers use POSIX APIs: macOS/Linux, or WSL on Windows. Native Windows filing is not supported.

<details>
<summary>Manual installation or an existing setup</summary>

For a new Codex installation:

```sh
mkdir -p ~/.agents/skills
git clone https://github.com/hwang847/codex-paper-reader.git ~/.agents/skills/literature-workflow
```

Already installed under `~/.codex/skills` or another supported location? Ask Codex to update that copy while preserving your changes; do not install a duplicate. If the skill is not detected, restart the Codex session.

</details>

[Changes](CHANGELOG.md) · [Customize or contribute](CONTRIBUTING.md) · [License](LICENSE)
