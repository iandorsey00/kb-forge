# 使用操作系统为 KB Forge 定时备份

[English](scheduled-backups.md) · 简体中文

如果需要在 KB Forge 编辑器关闭时备份，请使用操作系统的计划任务。KB Forge v0.5.0 已提供所需命令。可让系统每小时检查一次，由 KB Forge 判断是否需要创建新备份。以下配置约每 24 小时创建一次备份，如果某次检查错过，系统仍可在下次检查时补上。

## 准备与测试

在知识库的 `kbforge.yaml` 顶层 JSON 对象中添加以下属性：

```json
"scheduled_backup": {
  "directory": "../collection-backups",
  "interval_hours": 24
}
```

备份目录可使用相对于知识库的路径，也可使用知识库之外的绝对路径。父目录须已存在，运行任务的账户须有写入权限。请在另一块磁盘或经批准的备份存储中保留近期副本。生成的备份会保留，直到手动移除。

保存编辑并关闭 KB Forge。在应用项目目录中，用实际知识库路径测试：

```sh
python3 -m kbforge "/path/to/work-collection" --run-scheduled-backup
```

在 Windows 上手动测试时，可以用 `py` 代替 `python3`。首次成功运行会显示经过校验的 ZIP 路径。在备份间隔内再次运行会显示“No scheduled backup is due.”。为计划任务填写运行 KB Forge 的 Python 解释器的绝对路径。请将备份安排在知识库闲置时。如果编辑器通常保持开启，可使用应用内的定时备份，让备份等到应用内的写入完成后再执行。

## Windows · 任务计划程序

打开 **任务计划程序 → 创建任务**。使用可访问知识库和备份目录的日常账户。对于工作站，可先选择 **仅当用户登录时运行**。

| 设置 | 示例 |
| --- | --- |
| 名称 | `KB Forge collection backup` |
| 触发器 | 每天。在 **高级设置** 中设置每隔 **1 小时**重复，持续 **1 天**。 |
| 操作 | **启动程序** |
| 程序或脚本 | `C:\Users\Alex\dev\kb-forge\.venv\Scripts\python.exe` |
| 添加参数 | `-m kbforge "C:\Users\Alex\KB\work-collection" --run-scheduled-backup` |
| 起始于 | `C:\Users\Alex\dev\kb-forge` |

请替换示例路径。可用 `py -c "import sys; print(sys.executable)"` 查找解释器，也可使用虚拟环境中的 Python 路径。在任务设置中，将任务已在运行时的处理方式设为 **不启动新实例**。保存任务，右键选择 **运行**，再检查 **上次运行结果** 和备份目录。[Microsoft 任务计划程序操作文档](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskaction?view=windowsserver2025-ps)

## macOS · launchd

将以下内容保存为 `~/Library/LaunchAgents/local.kbforge.backup.plist`。如有需要，请创建 `LaunchAgents` 目录。替换所有示例路径。plist 中应使用绝对路径，包括 Python 解释器和 `WorkingDirectory` 中的应用项目目录。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.kbforge.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/alex/dev/kb-forge/.venv/bin/python</string>
    <string>-m</string>
    <string>kbforge</string>
    <string>/Users/alex/KB/work-collection</string>
    <string>--run-scheduled-backup</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/alex/dev/kb-forge</string>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>/Users/alex/Library/Logs/kbforge-backup.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/alex/Library/Logs/kbforge-backup.log</string>
</dict>
</plist>
```

使用当前登录的账户校验、加载并测试任务：

```sh
plutil -lint "$HOME/Library/LaunchAgents/local.kbforge.backup.plist" &&
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.kbforge.backup.plist" &&
launchctl kickstart "gui/$(id -u)/local.kbforge.backup"
```

检查 `~/Library/Logs/kbforge-backup.log` 和备份目录。此用户代理在登录会话中运行。[Apple launchd 任务文档](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

## Linux · cron

在已安装并运行 cron 的系统上，使用自己的用户计划表。运行 `crontab -e`，添加以下一行，并替换应用项目目录、解释器、知识库及日志路径。日志所在目录须已存在。

```cron
0 * * * * cd "/home/alex/dev/kb-forge" && "/home/alex/dev/kb-forge/.venv/bin/python" -m kbforge "/home/alex/KB/work-collection" --run-scheduled-backup >> "/home/alex/kbforge-backup.log" 2>&1
```

使用 `crontab -l` 确认任务已添加。在下一个整点之后检查日志和备份目录。[Linux crontab 格式说明](https://www.man7.org/linux/man-pages/man5/crontab.5.html)

## 验证恢复

将定时备份的 ZIP 解压到新目录。打开解压后包含 `kbforge.yaml` 的知识库目录，抽查几篇文章及其图片。[备份与恢复指南](../README.zh-CN.md#备份与恢复知识库)也介绍了单篇文章的恢复方法。

如果使用 KB Forge v0.4.0，同样可通过系统计划任务运行脚本，调用 `--backup-collection --output`，每次生成带时间戳的新 ZIP 路径。应用内的间隔检查和 `--run-scheduled-backup` 从 v0.5.0 起可用。
