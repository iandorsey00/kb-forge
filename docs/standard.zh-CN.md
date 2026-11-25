# KB Forge 文档标准

版本 0.1 · [English](standard.md) · 简体中文

本规范定义了可用常见工具阅读和编辑的知识库格式。**必需**表示知识库必须遵守的规则。**可配置**表示项目负责人可以在 `kbforge.yaml` 中自行设置。

## 知识库结构

| 路径 | 内容 |
| --- | --- |
| `kbforge.yaml` | 必需的配置文件，定义编号、语言、模板和品牌样式 |
| `registry/ids.yaml` | 编号登记表，键为已保留的编号，值为保留日期 |
| `articles/<id>/<language>.md` | 各语言版本的固定存放位置 |
| `articles/<id>/assets/` | 同一篇文章的各语言版本共用的图片目录 |
| `branding/` | 存放配置引用的可选品牌图片 |

使用 UTF-8 编码。配置、登记表和文件开头的元数据采用 JSON 对象语法，这种语法也符合 YAML 1.2。KB Forge 支持这一语法子集。元数据区块前后的 `---` 各自独占一行。正文使用 GitHub 风格的 Markdown，支持标题、列表、表格、代码和相对链接。品牌预览会过滤原始 HTML，并显示符合要求的本地图片。参见[完整的英文文章](../example/articles/FIELD-000001/en-US.md)及其[简体中文版](../example/articles/FIELD-000001/zh-CN.md)。

## 文章元数据

| 字段 | 要求 |
| --- | --- |
| `id` | 永久编号，与目录名一致。长度为 1 至 80 个字符，只能使用 ASCII 字母、数字、连字符和下划线，且以字母或数字开头。 |
| `language` | 已配置的语言标签，例如 `en-US` 或 `zh-CN`，须与文件主名完全一致 |
| `title`、`owner` | 必填的非空字符串 |
| `author` | 可选作者姓名。HTML 在标题下方显示作者；PDF 默认在正文前显示，也可通过自定义封面指定位置。作者姓名也会写入 PDF 属性。 |
| `type` | 必填，使用 `kbforge.yaml` 中的模板键 |
| `status` | `draft`（草稿）、`published`（已发布）或 `retired`（已停用） |
| `revision` | 正整数。修改对应语言版本时应递增。 |
| `updated_on` | 必填，采用 `YYYY-MM-DD` 格式 |
| `review_on` | 下一次复审日期，采用 `YYYY-MM-DD` 格式。缺少日期会产生警告。 |
| `description` | 可选的内容摘要 |
| `products`、`categories`、`regions`、`countries`、`tags` | 可选数组，元素为非空字符串 |
| `related` | 可选数组，元素为其他文章的编号 |
| `translation_of`、`source_revision` | 译文必填，分别记录同一篇文章的源语言和翻译所依据的确切修订号 |

模板规定必须出现的 Markdown 二级标题。可为不同语言配置不同的标题，参见演示配置。校验会检查结构、日期、译文状态和文件引用。发布前应核实技术步骤以及译文含义。

### 自定义元数据字段

在知识库的 `kbforge.yaml` 中添加可选的顶层对象 `metadata_fields`。将以下示例合并到现有配置中，然后重启 KB Forge。

```json
{
  "metadata_fields": {
    "internal": {"type": "boolean", "label": "内部使用", "default": false},
    "legacy_id": {"type": "integer", "label": "旧版编号"},
    "audience": {"type": "string", "label": "适用读者"}
  }
}
```

- 字段键名遵循文章编号的字符规则，并须避开 KB Forge 已使用的内置元数据键名。可用 `label` 设置编辑器中显示的名称。省略时，编辑器显示键名。
- `boolean` 表示布尔值 `true` 或 `false`，`integer` 表示整数，例如 `37`，`string` 表示非空白的单行文本。可选的 `default` 和已保存的值都须符合所声明的类型。布尔值和整数使用 JSON 字面量。
- 自定义字段显示在 **New article**（新建文章）和 **Edit article**（编辑文章）页面中，其值以相应的键名保存在该语言版本的 Markdown 文件开头的元数据区块中。默认值会预填到新建版本中，包括新建的译文。已有版本保留已保存的值。清空文本或整数字段，或将布尔字段设为 **Not set**（未设置），即可省略该键。选择 **False** 会保存 `false`。
- 保存文章时，未配置的现有元数据仍会保留。如果为文章中已有的字段添加配置，校验器会按声明的类型检查已有值。

示例中的 `internal` 字段用于记录预期读者。站点收录范围仍取决于文章状态和发布设置。

## 永久编号、译文和地区

配置 `identifiers.prefix`（前缀）、`separator`（分隔符，`-` 或 `_`）、`digits`（位数，1 至 12）和 `start`（起始正整数）。编号保留后，即使标题、地区或其他元数据发生变化，也请继续使用该编号。文章停用或移除后，仍应保留登记记录，以免重复使用编号。新的配置仅用于此后分配的编号。历史编号及导入编号可以沿用先前格式，但须符合永久编号的字符要求。

每个编号有一个源语言版本，每种语言最多有一个版本。翻译时沿用原编号，创建对应语言的文件，并记录源语言及其修订号。源文章发生变化后，校验会发出警告，直到译文完成复审并更新 `source_revision`。任何已配置的语言都可以作为源语言，文章也可以只提供一种语言版本。

使用 `regions` 和 `countries` 表明适用范围。全球适用的文章可以填写 `["Global"]`。地区补充说明应拥有独立编号，并通过 `related` 和 Markdown 相对链接关联全球通用文章。独立的地区规程可以声明自己的适用范围。语言标签表示正文所用语言。

## 图片、链接和品牌样式

将图片保存在文章的 `assets/` 目录下。名称可使用 ASCII 小写字母、数字和连字符，扩展名为 `.png`、`.jpg`、`.gif` 或 `.webp`。使用相对引用，例如 `![已选中 HDMI 1](assets/input-selector.png)`。用对应版本的语言填写替代文字，说明图片展示的内容。上传时保留图片的原始字节，文件名冲突时会加上数字后缀。简短的文件名便于阅读和迁移。

可以在图片引用后紧接 Pandoc 图片宽度提示。可使用 `1%` 至 `100%` 的整数百分比，以可用正文宽度为基准，也可使用 `1px` 至 `10000px` 的像素宽度。`{width=200px}` 和 `{width=200}` 均表示 200 像素。HTML 和 PDF 均保留宽高比，且图片宽度不超过可用空间。PDF 中 96 像素等于 72 磅，较高的图片还可进一步缩小以适应页面。普通 GFM 查看器可能会将宽度提示作为图片旁的文字显示。

```markdown
1. 选择输入源。

   ![已选中 HDMI 1](assets/input-selector.png){width=60%}
```

在图片前留一个空行，并将图片缩进至列表项的正文位置，使其仍属于同一个列表项。

使用相对路径链接其他文章版本，例如 `../FIELD-000002/en-US.md`。外部文本链接可使用 HTTP、HTTPS 或 mailto。在 `kbforge.yaml` 中配置 `branding.name`、可选的六位十六进制颜色 `color` 和可选的品牌图片文件名 `logo`。品牌样式应独立于文章正文。

## 文章生命周期与迁移

1. 创建草稿并保留编号，填写负责人和复审日期。
2. 补齐模板规定的内容，检查资源和链接，运行校验，并请他人核实操作步骤。准备分发时将状态设置为 `published`。
3. 修改后递增修订号并更新日期，复审引用旧修订号的译文。
4. 将过时版本设为 `retired`，并保留编号登记记录。

迁移时，复制整套知识库目录，包括登记表和资源文件。可使用任意文本编辑器打开 Markdown 文件。手动修改时应保留目录结构与元数据，递增所编辑版本的修订号，并保持相对链接有效。导入现有编号时，把各语言版本放入对应的编号目录，检查编号冲突，并在 `registry/ids.yaml` 中登记。可使用其他 Markdown 渲染工具及其打印功能独立发布文章，并通过该工具的主题恢复品牌样式。

KB Forge 通过本地文件系统上的独占锁分配编号。编号已分配但文章写入失败时，应保留该编号。若进程中断后遗留 `registry/allocate.lock`，须确认没有正在写入的进程，再删除锁文件。0.1 版暂未支持分布式编号分配和其他格式的自动迁移。每个知识库应由单个进程写入。

## 品牌样式与发布

`kbforge.yaml` 中可选的 `publishing` 对象通过常规文件名和设置描述输出样式。将这些资源放在 `branding/` 中。文章和主题均可通过普通文件定义，知识库本身无需提供可执行文件。

| 设置 | 含义 |
| --- | --- |
| `branding.logo` | 已配置的知识库标识 |
| `publishing.cover_image` | 自动生成封面时使用的图案。封面还会显示标题、编号、修订号和更新日期。 |
| `publishing.html_cover_image` | 浏览器文章视图和静态 HTML 导出的可选封面图。省略时沿用 `cover_image`；设为 `null` 可在 HTML 中隐藏封面图。PDF 封面使用独立设置。 |
| `publishing.header_image`、`publishing.footer_image` | 在分页 PDF 中重复显示的可选页眉、页脚图片，在 HTML 中各显示一次 |
| `publishing.paper` | `A4`（默认）或 `Letter` |
| `publishing.body_font_size` | 分页 PDF 的正文字号，单位为磅，范围为 8 至 18，默认为 11 |
| `publishing.toc_depth` | PDF 可点击目录所包含的 Markdown 最深标题级别，范围为 0（关闭）至 6，默认为 2 |
| 文章的 `cover_pdf` | `branding/` 中的可选 PDF 文件名。第一页替换自动生成的封面并确定纸张尺寸。请使用未旋转且页面坐标原点为零的单页 PDF。 |

HTML 页面显示品牌图片和 HTML 标题区。在 **Publish**（发布）中打开品牌 PDF，即可查看导入的 PDF 封面和带页码的目录。PDF 内页使用知识库标识和图片，并显示文档编号、修订号、更新日期及页码。渲染器会为引用文字添加底色，并在空间允许时让标题与后续内容的开头留在同一页。其他发布工具也可以读取相同的元数据及文件。

### 工作区品牌样式与字体

可选的 `workspace` 对象控制 KB Forge 界面及导出站点的外层布局。可设置 `name`、`branding/` 下的可选 `logo` 文件名，以及六位十六进制颜色 `accent`、`navigation` 和 `background`。导出首页和文章导航优先使用工作区名称和标识，默认沿用知识库名称和标识。站点链接、首页页眉和页面背景沿用对应的配色。建议使用深色强调色和导航栏背景搭配白色文字，并使用浅色背景搭配深色正文。文章本身的样式（包括 PDF 图片）由 `branding` 和 `publishing` 控制。

### 发布字体

将 TrueType 字体放在知识库的 `branding/` 目录中。要使用以下示例字体，请从 `example/branding/` 将所需字体及对应的 SIL 开放字体许可证复制到知识库的 `branding/` 目录。将下方的相关设置合并到现有 `kbforge.yaml`，然后重启 KB Forge。

- Inter Variable 4.1 正体和斜体，用于文档正文。[许可证](../example/branding/Inter-OFL.txt)
- Noto Sans CJK SC 2.004，用于简体中文。此地区版本约为 17 MiB。[上游项目](https://github.com/notofonts/noto-cjk/tree/Sans2.004) · [许可证](../example/branding/NotoSansCJK-OFL.txt)
- Source Code Pro 2.042 常规字重，用于等宽文本。[上游项目](https://github.com/adobe-fonts/source-code-pro/releases) · [许可证](../example/branding/SourceCodePro-OFL.txt)

在 `kbforge.yaml` 中加入所需设置。以下示例使用全部三个字体族：

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

- 定义字体族时，必须提供 `fonts.regular`。静态字体族还可分别提供 `bold`、`italic` 和 `bold_italic` 文件。可变字体的正体和斜体文件可分别提供各自的字重。如果没有单独的斜体文件，带有 `ital` 或 `slnt` 轴的正体文件也可提供倾斜字形。
- `font_weights` 为可选项。正文和图注默认使用 400，标题默认使用 700。各项均接受 1 至 1000 的整数。Markdown 加粗至少使用字重 700，强调使用斜体，嵌套强调可同时应用两种样式。可变字体根据 `wght` 轴的有效范围应用所需字重。PDF 中其他轴使用默认值，`ital` 和 `slnt` 可用于选择字形样式。静态字体族在 PDF 中会选用所需样式里字重最接近的字体。没有斜体时会使用正体。
- `font_fallbacks` 可将语言标签或 `default` 映射到字体文件名或另一组字体配置。KB Forge 依次尝试主字体、匹配语言的回退字体、默认回退字体及其他已配置的回退字体。PDF 缺少中文字形时，还可尝试系统的中日韩字体。最后尝试内置的 Noto Sans Symbols 2，覆盖 ☐、☑、☒、✓ 等符号。此回退无需配置，PDF 会嵌入实际使用的字形。如果所有字体均无对应字形，导出会提示具体字符。[上游版本](https://github.com/notofonts/symbols/releases/tag/NotoSansSymbols2-v2.008) · [SIL OFL 1.1 许可证](../kbforge/resources/NotoSansSymbols2-OFL.txt)
- `code_font` 为可选项，接受 TrueType `.ttf` 文件名。请选择等宽字体，用于 PDF 围栏代码块和 HTML 中的行内及围栏代码，包括标记为 `text` 的代码块。HTML 默认使用系统等宽字体。PDF 代码默认使用 Courier，并使用发布字体族或其回退字体补足其他字形。
- 交互式文章查看器和导出的 HTML 使用本地 TrueType `.ttf` 文件，通过 CSS 声明字重范围。导出的站点包含引用的字体和许可证说明，供离线使用。PDF 通过 FontTools 在内存中生成可变 TrueType 字体的静态实例，并嵌入所需字形。PDF 支持 TrueType 字体集合（`.ttc` 的首个字体）。目前不支持 CFF 和 CFF2 OpenType 轮廓。
- 仍可通过 `publishing.font` 指定单个字体。PDF 依次采用 `publishing.fonts`、`publishing.font`、`KBFORGE_PDF_FONT` 环境变量中的绝对路径，最后使用内置字体。环境变量仅用于 PDF。已有知识库无需迁移配置。
- 主题包会保留引用的字体、许可证说明和设置。共享自定义字体前，请确认再分发许可，并在 `font_licenses` 中列出随附的版权或许可证文件名。[Inter 官方发布](https://github.com/rsms/inter/releases) · [SIL 开放字体许可证常见问题](https://openfontlicense.org/ofl-faq/)

### 自定义 PDF 封面布局

在 `kbforge.yaml` 中设置 `publishing.cover_layout`，即可自定义封面元素的位置。每个元素占一个矩形区域。坐标 `x`、`y` 分别是距页面左边和上边的百分比，`width`、`height` 分别是占页面宽度和高度的百分比。

```json
"cover_layout": [
  {"image": "logo", "x": 72, "y": 8, "width": 18, "height": 7, "align": "right"},
  {"field": "title", "x": 10, "y": 21, "width": 80, "height": 18, "size": 28, "bold": true},
  {"image": "cover_image", "x": 10, "y": 43, "width": 80, "height": 35, "align": "center"},
  {"field": "updated_on", "x": 10, "y": 88, "width": 80, "height": 5, "size": 11}
]
```

- `image` 可使用 `logo`、`cover_image`、`header_image` 或 `footer_image`。图片保持原有比例。未配置的图像会跳过。
- `field` 可使用 `title`、`id`、`revision`、`updated_on`、`owner`、`author`、`status`、`language` 或 `organization`。`text` 用于固定文字。文字可设置字号 `size`（单位为点，默认 12）、粗体 `bold`（默认关闭）和六位十六进制颜色 `color`（默认 `#202020`）。
- `align` 可设置为 `left`、`center` 或 `right`。元素从各自区域的顶部开始，按列表顺序绘制。文字超出区域时，导出会提示调整布局。

自定义封面只显示列表中的元素。省略此设置即可使用内置封面。文章的 `cover_pdf` 优先。主题 ZIP 包含封面布局。修改知识库配置后，请重启 KB Forge，然后通过 **Open branded PDF** 预览。

### 手动迁移文章编号

更改已分配的编号前，请停止 KB Forge 并备份知识库。在项目目录中先预览受影响的文件，再明确执行迁移：

```sh
python3 -m kbforge work-collection --renumber OLD-00001 NEW-00001
python3 -m kbforge work-collection --renumber OLD-00001 NEW-00001 --force
python3 -m kbforge work-collection --validate
```

工具会一并移动所有语言版本及共享资源，在各版本的 `previous_ids` 中记录旧编号，并保留新旧编号。它会更新 `related` 和文章间常规的 Markdown 相对链接。请另行检查自定义元数据和外部链接，并重新导出受影响的 PDF 或 HTML。

## 文章包

**文章包**是一个目录，包含同一篇文章的各语言版本和共享图片。其内容结构与 `articles/<id>/` 目录一致：

```text
my-article/
  en-US.md
  zh-CN.md
  assets/
    input-selector.png
```

- 至少包含一个 `<language>.md` 文件。每个版本都须遵循上述元数据规则，并使用目标知识库已配置的语言和文档类型。各版本须使用同一有效 `id`。文章包目录名可以与编号不同。包含译文时，也须包含源语言版本。
- `assets/` 为可选目录，可包含符合命名规则的 PNG、JPG、GIF 或 WebP 图片，每张最多 8 MiB。请使用 `assets/input-selector.png` 等相对路径引用图片。包内只应包含文章版本和资源文件，且不支持符号链接。知识库级别的品牌资源须已安装在目标知识库中。
- 目标知识库及其编号登记表中均不得已有该编号。如需为已有文章添加语言版本，请在该文章的目录中管理。

请在导入前停止 KB Forge，并在项目目录中运行：

```sh
python3 -m kbforge work-collection --import-package /path/to/my-article
```

KB Forge 会根据目标知识库校验导入的文章及其引用，报告警告并登记文章编号。存在校验错误时会中止导入。源文章包仍可继续编辑或复用。新建文章的默认编号规则不影响文章包中指定的编号。

## 知识库批量标准迁移

标准变更时，可使用具名迁移升级现有文章文件。每项迁移均有明确的源文件转换规则。运行 `python3 -m kbforge --help` 可查看可用迁移。省略 `--force` 时，只会列出受影响的文章版本，不写入更改。

`author` 迁移会用指定姓名填充缺失、为 null 或为空白的作者字段。已有署名、正文、文章编号和修订日期均会保留。仅当待署名文章均由同一作者撰写时使用。执行前请停止 KB Forge 并备份知识库。

```sh
python3 -m kbforge work-collection --migrate author --author "Example Author"
python3 -m kbforge work-collection --migrate author --author "Example Author" --force
```

重新导出 HTML 和 PDF，即可更新已发布的副本。
