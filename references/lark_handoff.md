# Feishu/Lark Artifact Handoff

This integration publishes selected literature artifacts. Group agents, bot deployment, general office administration, and background sync are outside this skill.

Use the official `lark-cli` and its installed-version help/skills for current commands. If missing, verify the official package and help install it when authorized. Reuse an appropriate existing profile; do not create or replace credentials by default. Authenticate only for the requested destination and capability; never print secrets.

Resolve both the selected local files and the exact Drive folder or Wiki node before writing. The user's explicit request to publish those files there is authorization; ask only for missing scope or additional actions. Preview when supported. Overwriting, deleting, changing sharing, or syncing requires authorization for that action and target, not just an earlier upload request.

Prefer Drive attachments for PDFs, native Markdown for Markdown artifacts when supported, and Docs for a requested online document. A Wiki node is not a Drive folder: use the appropriate domain guide. HTML with relative images needs its assets packaged or separately published with corrected links; uploading the HTML alone does not publish a functioning website.

After publishing, return the resulting links and corresponding local paths. Keep the local source authoritative unless another ownership/sync policy was requested. Report permission or tenant restrictions as blockers; do not try to bypass them or expand account scope silently.
