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

Use UTF-8. Configuration, the registry, and front matter use JSON object syntax, which is valid YAML 1.2. KB Forge accepts this subset. Keep the two front matter delimiters as standalone `---` lines. The body uses GitHub-flavored Markdown, including headings, lists, tables, code, and relative links. The branded viewer strips raw HTML and renders supported local images. See [a complete English article](../example/articles/FIELD-000001/en-US.md) and [its Chinese edition](../example/articles/FIELD-000001/zh-CN.md).

## Article metadata

| Field | Requirement |
| --- | --- |
| `id` | Permanent identifier, matching the directory. Use 1–80 ASCII letters, digits, hyphens or underscores, beginning with a letter or digit. |
| `language` | Configured language tag such as `en-US` or `zh-CN`, matching the filename stem exactly |
| `title`, `owner` | Required nonempty strings |
| `author` | Optional author name. HTML shows it below the title, and PDF shows it before the article body unless a custom cover places it. The name also appears in PDF properties. |
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

### Custom metadata fields

Add an optional top-level `metadata_fields` object to the collection's `kbforge.yaml`. Merge this example into the existing configuration and restart KB Forge.

```json
{
  "metadata_fields": {
    "internal": {"type": "boolean", "label": "Internal", "default": false},
    "legacy_id": {"type": "integer", "label": "Legacy ID"},
    "audience": {"type": "string", "label": "Audience"}
  }
}
```

- Use the same character rules as for article IDs for field keys, and choose keys unused by KB Forge's built-in metadata. Use the optional `label` to set the name shown in the editor. Otherwise, the editor displays the key.
- Use `boolean` for `true` and `false`, `integer` for whole numbers such as `37`, or `string` for nonblank, single-line text. Both the optional `default` and any stored value must match the declared type. Use JSON literals for booleans and integers.
- Each field appears on **New article** and **Edit article**, and its value is saved under its own key in that language edition's Markdown front matter. Defaults prefill new editions, including new translations. Existing editions stay as saved. Clear a text or integer field or choose **Not set** for a boolean to omit its key. Choosing **False** stores `false`.
- Existing metadata without a definition stays in the article when you save it. If you define a field already used in your articles, the validator checks any existing values against the new type.

The example `internal` flag records intended audience. Site inclusion continues to follow article status and the publishing settings.

## Permanent IDs, translations, and regions

Choose `identifiers.prefix`, `separator` (`-` or `_`), `digits` (1–12), and `start` (a positive integer). After reservation, keep the ID when a title, region, or other metadata changes. Keep registry entries when articles are retired or removed. This prevents reusing their IDs. New settings apply to newly reserved IDs. Historical and imported IDs can use earlier formats if they satisfy the permanent ID syntax.

Each ID has one source edition and at most one edition per language. To translate, retain the ID, create another language file, and record the source language and revision. When the source changes, the validator warns until the translation is reviewed and its `source_revision` is updated. Any configured language may be the source. A single-language article is valid.

Express applicability through `regions` and `countries`. A global article can use `["Global"]`. Give a regional addendum its own ID and link it to the global article using `related` and a relative Markdown link. A standalone regional procedure can declare its own applicability. The language tag identifies the language of the text.

## Images, links, and branding

Store images under the article's `assets/` directory. Use lowercase ASCII letters and digits with optional hyphens, and a `.png`, `.jpg`, `.gif`, or `.webp` suffix. Write relative references such as `![HDMI 1 selected](assets/input-selector.png)`. Use alternative text to convey what the image shows in the language of the edition. The uploader keeps the image bytes and adds a numeric suffix if the filename is taken. Short names make paths easier to read and move.

You can add a Pandoc image width hint immediately after the image reference. Use a whole percentage of the available width from `1%` to `100%`, or a pixel width from `1px` to `10000px`. Both `{width=200px}` and `{width=200}` mean 200 pixels. HTML and PDF preserve proportions and cap the width at the available space. In PDF, 96 pixels equal 72 points, and tall images can be scaled down further to fit the page. Plain GFM viewers may show the width hint as text beside the image.

```markdown
1. Select the input.

   ![HDMI 1 selected](assets/input-selector.png){width=60%}
```

Indent the image to the list item's text column and leave a blank line before it. This keeps the image within the same list item.

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
| `publishing.html_cover_image` | Optional artwork for the browser article view and static HTML export. Omit to reuse `cover_image`, or set to `null` to hide cover artwork in HTML. The PDF cover uses its own settings. |
| `publishing.header_image`, `publishing.footer_image` | Optional page artwork, repeated in paginated PDF output and shown once each in HTML |
| `publishing.paper` | `A4` (default) or `Letter` |
| `publishing.body_font_size` | Paginated PDF body size in points, 8 to 18. Default is 11. |
| `publishing.toc_depth` | Deepest Markdown heading level included in the linked PDF contents, from 0 (off) to 6. Default is 2. |
| Article `cover_pdf` | Optional filename in `branding/`. The first page replaces the generated cover and sets the paper dimensions. Use a single-page, unrotated PDF with a zero-origin media box. |

The HTML view displays the collection artwork and an HTML title block. To see an imported PDF cover and the paginated contents, open the branded PDF from **Publish**. PDF interior pages use the collection logo and artwork with the document ID, revision, update date, and page number. The renderer shades blockquote text and keeps headings with the start of their content where space permits. Third-party renderers can use the same metadata and files.

### Workspace branding and fonts

The optional `workspace` object controls the KB Forge interface and the exported site's outer layout. Set `name`, an optional `logo` filename under `branding/`, and `accent`, `navigation`, and `background` as six-digit hex colors. Exported homepages and article navigation use the workspace name and logo when set, with the collection name and logo as defaults. The colors carry through to site links, the homepage header, and the page background. Use dark accent and navigation colors for white labels and a light background for dark text. The `branding` and `publishing` settings control the article itself, including PDF artwork.

### Publication fonts

Place TrueType font files under the collection's `branding/` directory. The example collection includes optional, unmodified font files with their SIL Open Font License notices. To use the example fonts in your own collection, copy the chosen font and its notice from `example/branding/` to your collection’s `branding/` directory. Merge the relevant settings below into your existing `kbforge.yaml` and restart KB Forge.

- Inter Variable 4.1 upright and italic for document text. [License](../example/branding/Inter-OFL.txt)
- Noto Sans CJK SC 2.004 for Simplified Chinese coverage. This regional build is about 17 MiB. [Upstream](https://github.com/notofonts/noto-cjk/tree/Sans2.004) · [License](../example/branding/NotoSansCJK-OFL.txt)
- Source Code Pro 2.042 Regular for monospace text. [Upstream](https://github.com/adobe-fonts/source-code-pro/releases) · [License](../example/branding/SourceCodePro-OFL.txt)

Add the settings you need to `kbforge.yaml`. This example uses all three families:

```json
{
  "publishing": {
    "fonts": {
      "regular": "InterVariable.ttf",
      "italic": "InterVariable-Italic.ttf"
    },
    "font_fallbacks": {"zh-CN": "NotoSansSC-VF.ttf"},
    "code_font": "SourceCodePro-Regular.ttf",
    "font_weights": {
      "body": 400,
      "heading": 600,
      "caption": 400
    },
    "font_licenses": ["Inter-OFL.txt", "NotoSansCJK-OFL.txt", "SourceCodePro-OFL.txt"]
  }
}
```

- `fonts.regular` is required when defining a family. For static families, optionally provide separate `bold`, `italic`, and `bold_italic` filenames. For a variable family, the upright and italic files can supply their respective weights. An upright file with an `ital` or `slnt` axis can supply a slanted face when a separate italic file is absent.
- `font_weights` is optional. Defaults are 400 for body and captions, and 700 for headings. Each accepts an integer from 1 to 1000. Markdown strong emphasis requests at least 700, emphasis requests italic, and nested emphasis combines them. Variable faces use the requested weight within the supported `wght` range. PDFs pin other axes at their defaults, except `ital` and `slnt` when selecting style. Static PDF families choose the closest configured weight in the requested style, then use upright if no italic face is available.
- `font_fallbacks` maps a language tag or `default` to a filename or another family object. KB Forge tries the primary face first, then matching language fallbacks, the default, and other configured fallbacks. The PDF renderer can also try a system CJK font for missing Chinese glyphs. It then tries the bundled Noto Sans Symbols 2 as a final fallback, including for ☐, ☑, ☒, and ✓. This fallback needs no collection settings and embeds the glyphs used in the PDF. It reports the missing character if no font covers it. [Upstream release](https://github.com/notofonts/symbols/releases/tag/NotoSansSymbols2-v2.008) · [SIL OFL 1.1](../kbforge/resources/NotoSansSymbols2-OFL.txt)
- `code_font` is optional and accepts a TrueType `.ttf` filename. Choose a monospace font for fenced PDF code and for inline and fenced code in HTML, including fences labeled `text`. HTML defaults to a system monospace font. PDF code defaults to Courier and uses the publication family or its fallbacks for additional glyphs.
- The interactive viewer and exported HTML use local TrueType `.ttf` files with CSS weight ranges. Exported sites include referenced font assets and license notices for offline use. PDFs use FontTools to instantiate variable TrueType faces in memory and embed the glyphs they use. TrueType-outline collections (`.ttc`, first face) are supported in PDF. CFF and CFF2 OpenType outlines are unsupported by this font pipeline.
- `publishing.font` remains supported as a single face. PDF precedence is `publishing.fonts`, then `publishing.font`, then the absolute path in `KBFORGE_PDF_FONT`, then the built-in fonts. The environment setting applies only to PDFs. Existing collections require no configuration migration.
- Theme bundles preserve referenced font files, notices, and settings. Confirm redistribution rights before sharing custom fonts and list any accompanying copyright or license files by filename in `font_licenses`. [Inter upstream releases](https://github.com/rsms/inter/releases) · [SIL Open Font License FAQ](https://openfontlicense.org/ofl-faq/)

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
- Use `field` with `title`, `id`, `revision`, `updated_on`, `owner`, `author`, `status`, `language`, or `organization`. Use `text` for literal text. Optional text settings are `size` in points (default 12), `bold` (default false), and a six-digit hex `color` (default `#202020`).
- Alignment is `left`, `center`, or `right`. Elements start at the top of their boxes and are drawn in list order. Export reports text that exceeds its box.

A custom layout draws only the specified elements on the cover. Omit it to use the built-in cover. An article's `cover_pdf` takes precedence. The layout travels with a theme ZIP. Restart KB Forge after changing collection settings, then use **Open branded PDF** to preview the cover.

### Deliberate ID migration

Stop KB Forge and back up the collection before changing an assigned ID. From the checkout, preview the affected edition paths, then apply the migration explicitly:

```sh
python3 -m kbforge work-collection --renumber OLD-00001 NEW-00001
python3 -m kbforge work-collection --renumber OLD-00001 NEW-00001 --force
python3 -m kbforge work-collection --validate
```

The tool moves all editions and shared assets together, records the old ID in each edition's `previous_ids`, and keeps both IDs reserved. It updates `related` and conventional relative Markdown links between articles. Review custom metadata and external links separately and regenerate any exported PDFs or HTML.

## Article packages

An **article package** is a directory containing one article, including all its language editions and shared images. Its contents use the same layout as a directory under `articles/<id>/`:

```text
my-article/
  en-US.md
  zh-CN.md
  assets/
    input-selector.png
```

- Include at least one `<language>.md` file. Each edition must follow the article metadata rules above, name a language and document type configured in the destination collection, and carry the same valid `id`. The package directory name can differ from the ID. Include the source edition when supplying translations.
- `assets/` is optional. It can contain PNG, JPG, GIF, or WebP files up to 8 MiB each, following the collection's image naming rules. Use relative image references such as `assets/input-selector.png`. Keep only article editions and assets in the package. Symbolic links are unsupported. Any collection-wide branding must already be installed in the destination.
- The ID must be unused in the destination, including its reservation registry. To add another language edition to an existing article, manage it in that article's directory.

Stop KB Forge before importing. From the checkout, run:

```sh
python3 -m kbforge work-collection --import-package /path/to/my-article
```

KB Forge validates the incoming editions and their references against the destination, reports warnings, and registers the imported ID. Validation errors abort the import. The source package remains available for editing or reuse. The defaults for new article ID allocation do not affect the package's explicit ID.

## Collection-wide standards migrations

KB Forge provides named migrations for upgrading existing article files when a standard changes. Each migration defines its own rules for transforming the source files. Run `python3 -m kbforge --help` for the available migrations. Running a migration without `--force` lists affected editions without writing changes.

The `author` migration fills missing, null, or blank author fields with a name you supply. It preserves existing credits, article content, IDs, and revision dates. Use it on a collection whose uncredited articles share that author. Stop KB Forge and back up the collection before applying the migration.

```sh
python3 -m kbforge work-collection --migrate author --author "Example Author"
python3 -m kbforge work-collection --migrate author --author "Example Author" --force
```

Export HTML and PDFs again to reflect changes in published copies.
