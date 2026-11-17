# Changelog · 更新日志

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
