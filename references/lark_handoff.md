# Feishu/Lark Handoff

Use this reference only after the user explicitly asks to place a research artifact in Feishu/Lark.

## Setup

1. Check `lark-cli --version`.
2. If absent, install the official CLI: `npx @larksuite/cli@latest install`.
3. Read the version-matched official guide with `lark-cli skills read lark-shared`, then read the target-domain guide.
4. If unconfigured, run `lark-cli config init --new` and relay its authorization URL unchanged with the required QR code. For user-space research work, authenticate only the needed domains, normally `docs`, `drive`, `markdown`, or `wiki`.

## Choose the Target

- Local Markdown share paths or survey artifacts: create a native Drive Markdown file with `lark-cli markdown +create`.
- Local PDFs, HTML notes, and attachments: use `lark-cli drive +upload`.
- A formatted cloud document: use `lark-cli docs +create` only after reading the official document-format guide.
- A Wiki destination: accept a concrete Wiki URL/node token and use its official guide; do not infer a parent location.

Use relative local file paths from the workspace for CLI file arguments. A folder URL/token or Wiki URL/token and explicit publication intent are required. Run the matching `--dry-run` command first when supported. Never overwrite existing cloud content, sync a directory, move cloud resources, delete, or change permissions unless the user separately confirms the exact target and action.

## After Publishing

Return the created URL/token and the local artifact path. Keep the local artifact authoritative unless the user asks for a two-way synchronization workflow.
