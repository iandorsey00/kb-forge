# KB Forge

[English](README.md) · 简体中文

KB Forge 是一套规划中的工具，用于创建、组织、校验和发布可迁移的知识库。文章采用 Markdown 编写，元数据保存在文件开头的 YAML 区块中，图片和附件以普通文件保存。即使组织日后更换 KB Forge，也应能使用常见工具阅读和维护原有知识库。

## 文档

最小可用版本（MVP）及每次改变文档所述操作流程的发布，都必须提供完整的英文和简体中文（`zh-CN`）文档。两个版本应便于查找，并提供相互跳转的链接。产品行为、配置或文档标准发生变化时，应在同一次变更中更新两个版本。

文档应包括以下内容：

- **文档标准。** 提供独立成章、具有版本号的规范，说明目录结构、元数据字段及允许值、永久文档编号和组织自定义前缀、资源文件的命名和存放位置、相对链接、文章之间的关系、译文管理、地区适用范围以及文章的生命周期。明确必遵规则、可配置的默认值和示例，并提供一篇附带资源文件的完整文章，供读者用 Markdown 编辑器查看。
- **快速入门与文章编写。** 说明如何安装和配置工具，并通过实例演示创建文章、添加图片、按元数据查找文章、修复校验发现的问题、预览带品牌样式的文章以及导出 PDF。
- **配置与维护。** 提供编号、元数据、模板、校验规则和品牌样式的配置示例。说明如何复审文章、更新译文、处理常见校验问题，以及如何使用常见工具继续使用和维护知识库。

两个版本应使用相同的命令、YAML 字段名和标识符。说明文字、标题、图注等面向读者的内容应提供对应译文。发布前，按两个语言版本的指引分别走完操作流程，检查示例文件和链接，并确认中文示例在 HTML 和 PDF 中均能清晰显示。

上述双语要求适用于 KB Forge 自身的文档和演示。各组织可以自行决定知识库支持哪些语言，单篇文章可以只提供一个语言版本。

## 运行最小可用版本

安装 Python 3.11 或更高版本，以及支持 GFM `attributes` 扩展的新版 Pandoc（可运行 `pandoc --list-extensions=gfm` 确认）。确保终端可以运行这两个程序。工作区无需云端账户或额外的 Python 软件包。分页 PDF 渲染器使用可选依赖。

在项目根目录中复制演示资料。应用会直接修改所打开的知识库。

```sh
cp -R example demo-work
python3 -m kbforge demo-work
```

在 Windows PowerShell 中，使用 `Copy-Item -Recurse example demo-work` 和 `py -m kbforge demo-work`。打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。按 Ctrl+C 退出。如果默认端口被占用，可加上 `--port 8766`。

### 体验演示流程

1. 打开 **New article**（新建文章）。选择 **Procedure**（操作规程），将来源保持为 **New article**，填写标题、负责人和未来的复审日期，再添加一个便于搜索的标签，例如 `demo-cable`。点击 **Create draft**（创建草稿）。在刚复制的演示资料中，新文章编号为 `FIELD-000005`。
2. 在 **Purpose**（目的）和 **Steps**（操作步骤）下填写正文。将光标移到需要插入图片的上一行，选择 PNG 或 JPEG 图片并填写描述，再点击 **Attach images**（添加图片）。最后点击 **Save changes**（保存更改），一并保存正文和图片引用。
3. 在 **Catalog**（目录）中搜索 `demo-cable`。打开文章，检查品牌样式和图片。通过 **Validation**（校验）查找问题。演示资料中的练习草稿故意缺少负责人、必要章节和图片，且已超过复审日期。
4. 点击 **Publish**（发布），再点击 **Print or save as PDF**（打印或另存为 PDF）。在 Chromium 中选择“另存为 PDF”，关闭浏览器自带的页眉页脚，并在保存前检查预览。打印样式会提供 A4 页边距、页码和带品牌样式的标题区。可打开 `FIELD-000001` 的中文版，检查汉字和截图是否清晰。如果预览中缺少汉字，请安装系统简体中文字体。
5. 用文本编辑器打开 `demo-work/articles/FIELD-000005/en-US.md`，查看文件开头的元数据和图片相对链接。直接打开该文章 `assets` 目录中的 PNG 或 JPEG 图片。

可通过 `python3 -m kbforge demo-work --validate` 在终端中校验知识库。退出状态码 1 表示存在错误。运行 `python3 -m unittest discover -s tests` 可执行自动化测试。

## 参考资料

参阅 [KB Forge 文档标准](docs/standard.zh-CN.md)，了解文件结构、元数据、文章生命周期、译文管理及迁移方法。[演示配置](example/kbforge.yaml) 提供了编号格式、文章模板和组织品牌样式的实例。

工作区仅监听本机地址，适合单人在本地维护知识库。浏览器界面为英文。可通过下文所述的分页渲染器或浏览器打印对话框导出 PDF。有关本地编号分配、Markdown 和导入的限制，请参阅文档标准。

### 发布带品牌样式的分页 PDF

在 macOS、Windows 或 Linux 上，使用运行 KB Forge 的同一 Python 环境安装可选依赖：

```sh
python3 -m pip install -r requirements-pdf.txt
python3 -m kbforge demo-work --export-pdf FIELD-000002 en-US --output article.pdf
```

也可以在 **Publish → Open branded PDF** 中查看结果。有关封面、品牌图片和中文字体，请参阅[发布设置](docs/standard.zh-CN.md#品牌样式与发布)。分页导出支持标题、段落、列表、代码块和本地图片。可通过浏览器打印保留 Markdown 表格及丰富的行内样式。

### 将主题迁移到另一个知识库

1. 在源电脑的 KB Forge 项目目录中导出主题。请使用尚不存在的 ZIP 文件名。

   ```sh
   python3 -m kbforge my-collection --export-theme my-theme.zip
   ```

2. 将 ZIP 复制到目标电脑。在已更新的 KB Forge 项目目录中使用现有知识库，或将附带的 `example` 目录复制为 `work-collection`。
3. 如果目标知识库正在运行，请先停止 KB Forge，然后导入主题并重新启动。

   ```sh
   python3 -m kbforge work-collection --import-theme my-theme.zip
   python3 -m kbforge work-collection
   ```

在 Windows PowerShell 中，可用 `py` 代替 `python3`，并通过 `Copy-Item -Recurse example work-collection` 复制示例知识库。如果 ZIP 位于其他目录，请填写实际路径。

ZIP 包含 `workspace`、`branding` 和 `publishing` 设置及其引用的资源。文章、编号、模板和文章专用 PDF 封面保留在各自的知识库中。如需备份目标主题，请先将其导出到另一个 ZIP。导入会替换这三个设置区块；若已有同名但内容不同的资源，导入会在更新设置前停止。

### 备份与恢复知识库

先保存文章并停止 KB Forge，再从应用目录运行以下任一命令。请选择尚未使用的 ZIP 文件名，并保存到知识库以外的现有目录。

```sh
python3 -m kbforge ../collections/work-collection --backup-collection --output ../work-backup.zip
python3 -m kbforge ../collections --backup-all-collections --output ../collections-backup.zip
```

在 Windows 上，可使用 `py` 代替 `python3`。第二条命令通过 `kbforge.yaml` 识别指定父目录下的知识库，只查找直接子目录。备份包含整个知识库，包括文章、编号、配置、品牌样式和本地资源。命令会校验 ZIP，并拒绝符号链接和特殊文件。请将一份备份存放在应用和知识库目录之外。

恢复时，将 ZIP 解压到新目录。启动 KB Forge 时，传入包含 `kbforge.yaml` 的已解压知识库目录，例如 `python3 -m kbforge ../restored/work-collection`。切换之前，请打开几篇文章并检查图片。如果只恢复一篇文章，请使用[文章包导入](docs/standard.zh-CN.md#文章包)。即使自动编号从 2 开始，仍可导入未使用且未预留的 `00001` 号。

### 更新应用

通过 Git 克隆安装时，可选择 **Updates → Check and install update**（更新 → 检查并安装更新），也可停止服务后，从应用目录运行以下命令。

```sh
python3 -m kbforge --update
```

KB Forge 会获取当前分支所跟踪的远程分支，并仅通过快进方式更新。Git 会阻止覆盖冲突的本地文件。如果受 Git 跟踪的修改阻止更新，可用 `git status --short` 查看。如果存在仅本地拥有的提交，请通过 Git 处理。更新功能跟踪上游分支，与发布标签相互独立。通过界面更新后，按 **Ctrl+C** 停止服务，再重新启动。如果可选的 PDF 依赖有变更，请重新执行上文的安装命令。

如果通过 ZIP 安装，请将[新版程序](https://github.com/iandorsey00/kb-forge/releases)解压到与旧版并列的新目录，并在启动时传入现有知识库路径。建议将知识库放在应用目录之外，以便单独替换软件。请先备份知识库，并确认新版可以打开，再移除旧版。

### 创建空白知识库

在项目目录中运行以下命令，指定一个尚不存在的目录：

```sh
python3 -m kbforge work-collection --init --name "技术支持知识库" --prefix SUPPORT --digits 5
python3 -m kbforge work-collection
```

该命令创建最小配置、空编号登记表、空文章目录和通用文章模板。使用 `--language` 设置首选语言，默认值为 `en-US)。之后可导入主题 ZIP 以应用品牌样式。在 Windows PowerShell 中，可使用 `py` 代替 `python3`。

### 批量处理图片

先从演示文稿导出所需图片，或将截图复制到剪贴板。在文章编辑页，可以一次选择多个文件，将其拖入编辑器或附件表单，也可将剪贴板中的图片粘贴到编辑器。检查每张图片的替代文字，按需设置 **Width for this batch (%)**（本批图片宽度），然后点击 **Attach images**（添加图片）。Markdown 引用会按队列顺序插在光标所在行下方。图片文件会立即写入资源目录。请保存草稿以保留引用。

如果图片属于列表项，请将光标放在包含列表标记的那一行，KB Forge 会自动设置缩进。如需手动调整，请按列表项正文前的字符数设置 **Indentation for list images**（列表图片缩进），将列表标记计入。比如，`1. 步骤` 缩进 3 个空格，`- 步骤` 缩进 2 个空格。之后可用 `{width=60%}` 调整单张图片的宽度。参阅 [Markdown 示例](docs/standard.zh-CN.md#图片链接和品牌样式)。如果放弃草稿，可通过校验查找未引用的资源。

### 导出静态 HTML 站点

```sh
python3 -m kbforge work-collection --export-html --output published-site
```

每次导出请使用新目录。结果包括索引页、共享样式表，以及每个已发布语言版本的品牌页面。图片嵌入页面，文章链接使用相对路径。可在本地打开 `index.html`，或将整个目录复制到经批准的内部静态站点。对于 SharePoint，可将 PDF 上传到文档库，或在现代页面中链接到单独托管的站点。

### 管理字体、编号与版本

如需统一拉丁字母 PDF 字体，可将 Inter 等静态 TrueType 字体放入 `branding/`，并在 `publishing.font` 中填写文件名。中文版需要包含中文字形的字体。修改字体后，从 Markdown 重新导出以更新分页。导入的 PDF 封面保留原有字体。

知识库移交后，已有文章应保留原编号。采用正式编号规则后，可为新文章使用新前缀。如果现有文章必须重新编号，请保留新旧编号对照表，并在元数据中保存原编号。更新引用，然后重新生成受影响的导出文件。

应用版本使用 `v0.1.0` 等 Git 标签，并记录在[更新日志](CHANGELOG.md)中。知识库格式与文章修订号独立于应用版本。应用内更新功能跟踪已配置的 Git 上游分支。
