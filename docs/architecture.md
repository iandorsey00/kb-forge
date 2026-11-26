# KB Forge architecture and priorities

English · [简体中文](architecture.zh-CN.md)

## How the product works

| Workflow | Current design |
| --- | --- |
| Capture and author | Create an edition from a template or import an existing article package. Edit portable Markdown and metadata in the local browser workspace. Images live beside the editions and are referenced by relative path. |
| Maintain and validate | Use registered article numbers and language-specific editions. Validation checks the collection, including review dates, links, assets, and revisions used by translations. Deliberate renumbering preserves historical identifiers in metadata. |
| Publish and retrieve | Pandoc supplies the document structure. Editor preview and HTML publication share a renderer. A separate paginated PDF renderer uses the same parsed Markdown and supports portable themes. Readers can search the exported site without running the editor or use the PDF library. |
| Collaborate and recover | Shared filesystem snapshots support publication preview, rollback, and source reconciliation. Editor and reader access use separate folders. Use a single designated publisher for cloud-synced storage. Verified ZIP backups can be extracted into a new folder. |
| Install and update | Run Python and Pandoc, with optional PDF dependencies. The app listens on loopback. The updater applies a Git fast-forward. Keep application code and collections in separate directories. |

The [documentation standard](standard.md) governs the collection files. Current changes require no migration. Existing Markdown and links continue to work in other compatible tools.

## First milestone

Recover unsaved Markdown and edited fields in the browser, preserve meaningful Markdown whitespace on save, open readable editions from validation findings, and flag references to retired material. The browser stores recovery copies separately from the collection and checks the saved edition before allowing restoration. A stale copy can be reviewed and copied manually. The ordinary editor retains its file-change check before writing.

Keep source and split-view editing for this milestone. A visual editor would need to round-trip nested lists, fenced blocks, attributes, and unknown constructs without modifying them. Browser-local recovery fits the current loopback workspace and avoids putting unreviewed work into publication snapshots or backups. Recovery is scoped to the browser profile, local address, and edition path. It does not transfer with the collection. Images attached to the collection are separate files.

## Priorities after this milestone

1. **Reduce intake and distribution work.** Test document conversion with representative editable source files, starting with formats Pandoc already handles. Offer reviewable drafts with local source references. Test a single-file offline publication against the existing site ZIP and PDF library for size, search, and portability.
2. **Improve maintenance and retrieval.** Continue deterministic validation and translation review. Prototype a published-only structured export with stable citations and applicability fields. Keep private evidence and source material separate from reader outputs.
3. **Simplify setup and recovery.** Evaluate a launcher and portable packaging against the actual macOS and Windows installation steps. Test dependency and update behavior before selecting a distribution strategy.

Revisit internal IDs, OCR, AI assistance, and renderer replacement when tests demonstrate a specific limitation. A new identifier scheme would require evidence that it improves reconciliation or stable references across collections. Evaluate extraction providers with English and Simplified Chinese samples before adoption. Existing format, collaboration, and publication choices remain documented in the [standard](standard.md) and [user guide](../README.md).
