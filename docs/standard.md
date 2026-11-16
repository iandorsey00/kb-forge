# KB Forge Documentation Standard

Version 0.1 · English · [简体中文](standard.zh-CN.md)

This specification defines a collection that can be edited and read using ordinary tools. **Required** describes the collection contract. **Configurable** means the project owner chooses a value in `kbforge.yaml`.

## Collection layout

| Path | Contents |
| --- | --- |
| `kbforge.yaml` | Required configuration for IDs, languages, templates, and branding |
| `registry/ids.yaml` | Reserved IDs as keys, with reservation dates as values |
| `articles/<id>/<language>.md` | Required location for each article edition |
| `articles/<id>/assets/` | Shared images for the language editions of one article |
| `branding/` | Optional branding image referenced by configuration |

Use UTF-8. Configuration, the registry, and front matter use JSON object syntax, which is valid YAML 1.2. The MVP accepts this subset. Keep the two front matter delimiters as standalone `---` lines. The body uses GitHub-flavored Markdown, including headings, lists, tables, code, and relative links. The branded viewer strips raw HTML and renders supported local images. See [a complete English article](../example/articles/FIELD-000001/en-US.md) and [its Chinese edition](../example/articles/FIELD-000001/zh-CN.md).

## Article metadata

| Field | Requirement |
| --- | --- |
| `id` | Permanent identifier, matching the directory. Use 1–80 ASCII letters, digits, hyphens or underscores, beginning with a letter or digit. |
| `language` | Configured language tag such as `en-US` or `zh-CN`, matching the filename stem exactly |
| `title`, `owner` | Required nonempty strings |
| `type` | Required template key from `kbforge.yaml` |
| `status` | `draft`, `published`, or `retired` |
| `revision` | Positive integer. Increase it when an edition changes. |
| `updated_on` | Required date in `YYYY-MM-DD` |
| `review_on` | Next review date in `YYYY-MM-DD`. A missing date produces a warning. |
| `description` | Optional summary |
| `products`, `categories`, `regions`, `countries`, `tags` | Optional arrays of nonempty strings |
| `related` | Optional array of other article IDs |
| `translation_of`, `source_revision` | Required on translations. Name the source language of the same article and record the exact source revision used. |

A template specifies the required second-level Markdown headings. Heading names can be configured separately for each language, as shown in the demo configuration. The validator checks structure, date and translation status, and file references. Review the technical steps and the meaning of the translation before publishing.

## Permanent IDs, translations, and regions

Choose `identifiers.prefix`, `separator` (`-` or `_`), `digits` (1–12), and `start` (a positive integer). After reservation, keep the ID when a title, region, or other metadata changes. Keep registry entries when articles are retired or removed. This prevents reusing their IDs. New settings apply to newly reserved IDs. Historical and imported IDs can use earlier formats if they satisfy the permanent ID syntax.

Each ID has one source edition and at most one edition per language. To translate, retain the ID, create another language file, and record the source language and revision. When the source changes, the validator warns until the translation is reviewed and its `source_revision` is updated. Any configured language may be the source. A single-language article is valid.

Express applicability through `regions` and `countries`. A global article can use `["Global"]`. Give a regional addendum its own ID and link it to the global article using `related` and a relative Markdown link. A standalone regional procedure can declare its own applicability. The language tag identifies the language of the text.

## Images, links, and branding

Store images under the article's `assets/` directory. Use lowercase ASCII letters and digits with optional hyphens, and a `.png`, `.jpg`, `.gif`, or `.webp` suffix. Write relative references such as `![HDMI 1 selected](assets/input-selector.png)`. Use alternative text to convey what the image shows in the language of the edition. The uploader keeps the image bytes and adds a numeric suffix if the filename is taken. Short names make paths easier to read and move.

Link to another edition with a relative path such as `../FIELD-000002/en-US.md`. External text links can use HTTP, HTTPS or mailto. Configure `branding.name`, an optional six-digit hex `color`, and an optional image filename `logo` in `kbforge.yaml`. Keep branding separate from article prose.

## Lifecycle and portability

1. Create a draft and reserve an ID. Set an owner and review date.
2. Complete the template, check assets and links, run validation, and have someone verify the procedure. Set the status to `published` when ready to distribute.
3. Increment the revision and update the date after a change. Review any translations that reference an older source revision.
4. Set obsolete editions to `retired`. Retain the ID reservation.

To move a collection, copy the entire directory, including its registry and assets. Open the Markdown files in any text editor. To edit manually, preserve the layout and metadata, increment the edition's revision, and keep relative links working. To import an existing ID, place the editions under that ID, check for collisions, and record the reservation in `registry/ids.yaml`. A Markdown renderer and its print functionality can publish articles independently. Reapply branding through the replacement renderer's theme.

KB Forge reserves IDs on the local filesystem using an exclusive lock file. A failed write after allocation may leave a reserved ID without an article. Keep that reservation. If an interrupted process leaves `registry/allocate.lock`, remove the lock only after confirming no writer is active. Distributed ID allocation and automatic migration from other formats are outside version 0.1. Keep one active writer per collection.

## Branded publishing

The optional `publishing` object in `kbforge.yaml` describes the output, using ordinary filenames and settings. Place its assets under `branding/`. The article source and theme require no executable files in the collection.

| Setting | Meaning |
| --- | --- |
| `branding.logo` | Existing collection logo |
| `publishing.cover_image` | Artwork for the generated cover, which also shows the article title, ID, revision, and update date |
| `publishing.header_image`, `publishing.footer_image` | Optional page artwork, repeated in paginated PDF output and shown once each in HTML |
| `publishing.paper` | `A4` (default) or `Letter` |
| `publishing.toc_depth` | Deepest Markdown heading level included in the linked PDF contents, from 0 (off) to 6. Default is 2. |
| Article `cover_pdf` | Optional filename in `branding/`. The first page replaces the generated cover and sets the paper dimensions. Use a single-page, unrotated PDF with a zero-origin media box. |

The HTML view displays the collection artwork and an HTML title block. To see an imported PDF cover and the paginated contents, open the branded PDF from **Publish**. PDF interior pages use the collection logo and artwork with the document ID, revision, update date, and page number. Third-party renderers can use the same metadata and files.

### Workspace branding and fonts

The optional `workspace` object controls the KB Forge interface. Set `name`, an optional `logo` filename under `branding/`, and `accent`, `navigation`, and `background` as six-digit hex colors. Use dark accent and navigation colors for white labels and a light background for dark text. The existing `branding` and `publishing` settings continue to control articles.

Use `publishing.font` to name a TrueType font file (`.ttf` or `.ttc`) under `branding/`, or set the local `KBFORGE_PDF_FONT` environment variable to an absolute path. KB Forge embeds the glyphs it uses. For Chinese documents it also tries Arial Unicode on macOS, Microsoft YaHei on Windows, and WenQuanYi Zen Hei on Linux. If those are unavailable, configure a CJK TrueType font with the required glyphs.

### Custom PDF cover layout

Set `publishing.cover_layout` in `kbforge.yaml` to place elements on the generated cover. Each element has a bounding box. Set `x` and `y` as percentages from the left and top edges of the page and `width` and `height` as percentages of page size.

```json
"cover_layout": [
  {"image": "logo", "x": 72, "y": 8, "width": 18, "height": 7, "align": "right"},
  {"field": "title", "x": 10, "y": 21, "width": 80, "height": 18, "size": 28, "bold": true},
  {"image": "cover_image", "x": 10, "y": 43, "width": 80, "height": 35, "align": "center"},
  {"field": "updated_on", "x": 10, "y": 88, "width": 80, "height": 5, "size": 11}
]
```

- Use `image` with `logo`, `cover_image`, `header_image`, or `footer_image`. Images retain their proportions. Unconfigured images are skipped.
- Use `field` with `title`, `id`, `revision`, `updated_on`, `owner`, `status`, `language`, or `organization`. Use `text` for literal text. Optional text settings are `size` in points (default 12), `bold` (default false), and a six-digit hex `color` (default `#202020`).
- Alignment is `left`, `center`, or `right`. Elements start at the top of their boxes and are drawn in list order. Export reports text that exceeds its box.

A custom layout draws only the specified elements on the cover. Omit it to use the built-in cover. An article's `cover_pdf` takes precedence. The layout travels with a theme ZIP. Restart KB Forge after changing collection settings, then use **Open branded PDF** to preview the cover.
