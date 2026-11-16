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

使用 UTF-8 编码。配置、登记表和文件开头的元数据采用 JSON 对象语法，这种语法也符合 YAML 1.2。最小可用版本支持这一语法子集。元数据区块前后的 `---` 各自独占一行。正文使用 GitHub 风格的 Markdown，支持标题、列表、表格、代码和相对链接。品牌预览会过滤原始 HTML，并显示符合要求的本地图片。参见[完整的英文文章](../example/articles/FIELD-000001/en-US.md)及其[简体中文版](../example/articles/FIELD-000001/zh-CN.md)。

## 文章元数据

| 字段 | 要求 |
| --- | --- |
| `id` | 永久编号，与目录名一致。长度为 1 至 80 个字符，只能使用 ASCII 字母、数字、连字符和下划线，且以字母或数字开头。 |
| `language` | 已配置的语言标签，例如 `en-US` 或 `zh-CN`，须与文件主名完全一致 |
| `title`、`owner` | 必填的非空字符串 |
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

## 永久编号、译文和地区

配置 `identifiers.prefix`（前缀）、`separator`（分隔符，`-` 或 `_`）、`digits`（位数，1 至 12）和 `start`（起始正整数）。编号保留后，即使标题、地区或其他元数据发生变化，也请继续使用该编号。文章停用或移除后，仍应保留登记记录，以免重复使用编号。新的配置仅用于此后分配的编号。历史编号及导入编号可以沿用先前格式，但须符合永久编号的字符要求。

每个编号有一个源语言版本，每种语言最多有一个版本。翻译时沿用原编号，创建对应语言的文件，并记录源语言及其修订号。源文章发生变化后，校验会发出警告，直到译文完成复审并更新 `source_revision`。任何已配置的语言都可以作为源语言，文章也可以只提供一种语言版本。

使用 `regions` 和 `countries` 表明适用范围。全球适用的文章可以填写 `["Global"]`。地区补充说明应拥有独立编号，并通过 `related` 和 Markdown 相对链接关联全球通用文章。独立的地区规程可以声明自己的适用范围。语言标签表示正文所用语言。

## 图片、链接和品牌样式

将图片保存在文章的 `assets/` 目录下。名称可使用 ASCII 小写字母、数字和连字符，扩展名为 `.png`、`.jpg`、`.gif` 或 `.webp`。使用相对引用，例如 `![已选中 HDMI 1](assets/input-selector.png)`。用对应版本的语言填写替代文字，说明图片展示的内容。上传时保留图片的原始字节，文件名冲突时会加上数字后缀。简短的文件名便于阅读和迁移。

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
| `publishing.header_image`、`publishing.footer_image` | 在分页 PDF 中重复显示的可选页眉、页脚图片，在 HTML 中各显示一次 |
| `publishing.paper` | `A4`（默认）或 `Letter` |
| `publishing.toc_depth` | PDF 可点击目录所包含的 Markdown 最深标题级别，范围为 0（关闭）至 6，默认为 2 |
| 文章的 `cover_pdf` | `branding/` 中的可选 PDF 文件名。第一页替换自动生成的封面并确定纸张尺寸。请使用未旋转且页面坐标原点为零的单页 PDF。 |

HTML 页面显示品牌图片和 HTML 标题区。在 **Publish**（发布）中打开品牌 PDF，即可查看导入的 PDF 封面和带页码的目录。PDF 内页使用知识库标识和图片，并显示文档编号、修订号、更新日期及页码。其他发布工具也可以读取相同的元数据及文件。

### 工作区品牌样式与字体

可选的 `workspace` 对象控制 KB Forge 界面样式。可设置 `name`、`branding/` 下的可选 `logo` 文件名，以及六位十六进制颜色 `accent`、`navigation` 和 `background`。建议使用深色强调色和导航栏背景搭配白色文字，并使用浅色背景搭配深色正文。文章样式仍由 `branding` 和 `publishing` 控制。

可通过 `publishing.font` 指定 `branding/` 下的 TrueType 字体文件（`.ttf` 或 `.ttc`），也可将本机环境变量 `KBFORGE_PDF_FONT` 设为字体的绝对路径。KB Forge 会嵌入所用字形。生成中文文档时，还会尝试 macOS 上的 Arial Unicode、Windows 上的微软雅黑及 Linux 上的文泉驿正黑。若这些字体不可用，请配置包含所需字形的中日韩 TrueType 字体。

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
- `field` 可使用 `title`、`id`、`revision`、`updated_on`、`owner`、`status`、`language` 或 `organization`。`text` 用于固定文字。文字可设置字号 `size`（单位为点，默认 12）、粗体 `bold`（默认关闭）和六位十六进制颜色 `color`（默认 `#202020`）。
- `align` 可设置为 `left`、`center` 或 `right`。元素从各自区域的顶部开始，按列表顺序绘制。文字超出区域时，导出会提示调整布局。

自定义封面只显示列表中的元素。省略此设置即可使用内置封面。文章的 `cover_pdf` 优先。主题 ZIP 包含封面布局。修改知识库配置后，请重启 KB Forge，然后通过 **Open branded PDF** 预览。
