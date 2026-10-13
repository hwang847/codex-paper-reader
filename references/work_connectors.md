# Work Connectors

Connect external services only for a requested literature task, such as archiving selected notes in Feishu/Lark. The host agent chooses and operates the tools; this skill has no connector runtime or required provider.

## Choose and Set Up

- Start with the requested outcome and reuse suitable installed tools and project conventions. Search GitHub when a CLI is needed; prefer official projects, verify ownership through the service's documentation, and check maintenance, platform support, and installation instructions. Explain third-party trust or capability gaps before proposing an alternative.
- Install only with authorization, using a project environment where practical or an appropriate existing installation. Inspect the installation commands before running them. Use the CLI's current help for authentication and the minimum required access; do not silently replace profiles or credentials. Report unsupported capabilities rather than inventing commands.

## Keep It in the Project

On first use, maintain a small workspace-local `connectors/README.md`, or reuse the project's existing connector inventory. Record the purpose, upstream repository, installed version, invocation/environment, non-secret configuration references, and verified or pending capabilities. Link it from the local `AGENTS.md` so future sessions can reuse the setup.

Keep this record in the user's workspace, not the shared skill. Use the CLI's credential store for secrets; never put tokens in instructions or tracked files. Keep sensitive local configuration and environment artifacts out of version control. Create only what the selected tool needs, not a provider catalog or installation framework.

## Use and Hand Off

Setting up a connection does not authorize uploading. For external writes, resolve the selected artifacts, account, and exact destination from the request; ask only for missing scope. Preview when supported. Deletion, overwriting, sharing changes, or ongoing sync need authorization for that action and target. After an uncertain write, check remote state before retrying.

Keep local sources unchanged. Preserve linked assets when exporting HTML; uploading an HTML file alone does not publish its images or a working website. Report permission or tenant restrictions without bypassing them.

Finish with what was configured, where it is recorded, what was actually verified, and any remaining user action. After publishing, return remote links and matching local paths. An unavailable connector must not block local reading or notes.
