# Scoped Surveys

Derive the research question, source set, and intended output from the request; clarify only what changes the synthesis. A quick comparison does not require a manifest. For a maintained review, use `survey init --title ... --scope ... --paper ...` with repeated `--paper` arguments and optional `--source <draft>`.

The command writes `surveys/<topic>/manifest.json` and `reading_pack.md`; it records scope and provenance, not survey prose. `survey init --update` replaces the selected scope explicitly. `survey refresh <query>` refreshes paths and reports unavailable sources.

Read relevant full sections, including evaluation when comparing evidence. Organize the synthesis around the research question; trace claims to sources and separate evidence, interpretation, and gaps. A selected local corpus is not automatically a comprehensive or systematic review.

Existing drafts registered as sources are read-only. `survey source add <draft> --move` relocates one to `surveys/sources/` only on request and preserves its bytes. Write generated prose separately. If the user explicitly requests editing an original draft, handle that as a document-editing task, not a source-refresh operation.
