# Changelog · 更新日志

## v0.8.1

- Match the HTML background colors for fenced text and blockquotes in PDFs.

### 简体中文

- 使 PDF 中围栏文本和引用块的底色分别与 HTML 保持一致。

## v0.8.0

- Group core fields on the New article screen and make additional details and custom metadata collapsible.
- Render Markdown task items with checkboxes in HTML and PDF, and use monospace for fenced text in HTML.
- Bundle Noto Sans Symbols 2 as the final PDF font fallback.
- Open branded PDFs in a new tab and suggest `<id> <title>.pdf` for downloads. Print from a PDF viewer.

### 简体中文

- 在新建文章页面集中显示核心字段，并支持折叠其他详细信息和自定义元数据。
- 在 HTML 和 PDF 中用复选框显示 Markdown 任务项，并在 HTML 中以等宽字体显示围栏文本。
- 内置 Noto Sans Symbols 2 作为 PDF 的最后回退字体。
- 在新标签页中打开品牌 PDF，下载时建议使用 `<编号> <标题>.pdf` 作为文件名。可通过 PDF 查看器打印。

## v0.7.0

- Redesign the article editor with a larger writing area, formatting controls, Write, Split, and Preview views, and a collapsible sidebar for article details, classification, and images.
- Show unsaved changes and support saving with Ctrl+S or ⌘S.
- Define custom string, integer, and boolean fields in `kbforge.yaml`. New editions can use configured defaults, and the validator checks stored values against their declared types.

### 简体中文

- 重新设计文章编辑器，扩大编写区域，提供格式工具以及编写、分屏和预览视图，并将文章详情、分类和图片放入可折叠的侧栏。
- 显示未保存的更改，并支持使用 Ctrl+S 或 ⌘S 保存。
- 在 `kbforge.yaml` 中定义字符串、整数和布尔类型的自定义字段。新建版本可使用默认值，校验器会检查已保存的值是否符合所声明的类型。

## v0.6.0

- Add article body search to the workspace and offline search to the redesigned exported site.
- Distinguish fenced text and code in PDFs with shaded, padded blocks that preserve indentation.
- Use static or variable TrueType families with real PDF weights, Markdown emphasis, multilingual fallback, and offline web font assets.
- Include optional Noto Sans CJK SC and Source Code Pro fonts with their license notices, and apply workspace branding to exported site navigation and homepages.
- Highlight the existing Updates link when a fast-forward app update is available.
- Document collection renaming and scheduled backups on Windows, macOS, and Linux.

### 简体中文

- 工作区支持搜索文章正文，重新设计的导出站点支持离线搜索。
- PDF 中的围栏文本和代码块带有底色和内边距，并保留缩进。
- 支持静态或可变 TrueType 字体族、PDF 字重、Markdown 强调、多语言回退和离线网页字体资源。
- 提供可选的 Noto Sans CJK SC 和 Source Code Pro 字体及许可证，并将工作区品牌样式应用于导出站点首页和导航。
- 有可快进应用的更新时，突出显示导航栏中已有的更新入口。
- 记录知识库重命名及 Windows、macOS 和 Linux 上的定时备份方法。

## v0.5.0

- Use `--export-site` to export a static site with branded PDFs and download links. The HTML and PDF for each edition sit side by side under `articles/<id>/`. Add `--html-only` for HTML-only output.
- Paginated PDFs render Markdown pipe tables with repeated headers on later pages.
- Publish versioned site releases to named filesystem destinations, preview edition changes, roll back, and copy the live snapshot for offline use.
- Clone editable sites and merge pushes from several editors. Automatically reassign independently allocated duplicate IDs and report conflicting file edits.
- Include a portable site manifest and show recent new and updated editions on published homepages.
- Schedule verified collection backups in the running app or through an operating system task.
- Document OneDrive and SharePoint distribution and show the fictional example collection in the READMEs.

### 简体中文

- 使用 `--export-site` 导出静态站点及品牌 PDF，页面均提供下载链接。同一语言版本的 HTML 和 PDF 并排保存在 `articles/<id>/` 下。添加 `--html-only` 可仅导出 HTML。
- 分页 PDF 支持使用竖线编写的 Markdown 表格，并在续页重复显示表头。
- 可预览文章版本变更，将站点版本发布到具名的文件系统目标，执行回滚，并复制当前发布快照以供离线阅读。
- 可克隆可编辑站点并合并多位编辑人员的推送。自动为独立分配的重复编号重新编号，并报告有冲突的文件修改。
- 导出站点时生成可移植的清单，并在发布首页显示近期新发布或更新的文章。
- 可通过运行中的应用或操作系统计划任务定时创建经过校验的知识库备份。
- 记录通过 OneDrive 与 SharePoint 分发站点的方法，并在两个 README 中加入虚构知识库的应用截图。

## v0.4.0

- Back up one or several complete collections to a verified ZIP.
- Update a Git checkout from the CLI or the app while preserving local collection folders.
- Use the taller editor to select, drop, or paste images and attach them in batches with optional display widths.
- Shade blockquotes, align images inside list items, keep headings with the start of their content, and use a configurable 11-point default body size in paginated PDFs.

### 简体中文

- 将一个或多个完整知识库备份到经过校验的 ZIP 文件。
- 可通过命令行或应用更新 Git 工作副本，并保留本地知识库目录。
- 在更高的编辑区中选择、拖入或粘贴图片，支持批量添加并设置显示宽度。
- 分页 PDF 为引用添加底色，对齐列表中的图片，让标题与正文开头同页，并采用可配置的默认 11 磅正文字号。

## v0.3.0

- Import article packages with Markdown editions and shared images. Validate against the destination collection and reserve the imported ID.
- Preview article ID migrations and apply them with an explicit `--force` flag. Preserve old ID reservations and update collection references.
- Choose separate cover artwork for browser articles and static HTML exports.
- Apply the workspace accent color to buttons and links.
- Display optional article authors in HTML and PDF.
- Preview and apply named collection-wide standards migrations, starting with author backfill.

### 简体中文

- 导入含 Markdown 文章版本和共享图片的文章包。根据目标知识库校验并登记导入的编号。
- 支持预览文章编号迁移，并通过 `--force` 明确执行。保留旧编号并更新知识库内的引用。
- 可为浏览器文章和静态 HTML 导出单独配置封面图。
- 工作区强调色现可应用于按钮和链接。
- 在 HTML 和 PDF 中显示可选的文章作者。
- 预览并执行具名的知识库批量标准迁移，首项迁移支持补填作者。

## v0.1.0

- Create a blank collection with configurable numbering and a generic template.
- Attach images at the editor cursor while retaining unsaved changes.
- Export published editions as a portable static HTML site.
- Includes branded PDF publishing, theme ZIP transfer, and fast-forward Git updates.

### 简体中文

- 创建空白知识库，支持自定义编号和通用模板。
- 在光标处插入图片，同时保留未保存的更改。
- 将已发布的文章版本导出为可迁移的静态 HTML 站点。
- 包含品牌 PDF 发布、主题 ZIP 导入导出，以及 Git 快进更新。
