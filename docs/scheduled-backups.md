# Schedule KB Forge backups with your operating system

English · [简体中文](scheduled-backups.zh-CN.md)

Use the operating system's scheduler when backups should run while the KB Forge editor is closed. KB Forge v0.5.0 already supplies the backup command. Set the scheduler to check hourly and let KB Forge decide when a new archive is due. This gives a daily backup with the example below and gives the scheduler another chance after a missed check.

## Prepare and test

In the collection's `kbforge.yaml`, add this property to the top-level JSON object:

```json
"scheduled_backup": {
  "directory": "../collection-backups",
  "interval_hours": 24
}
```

The backup directory is relative to the collection. It can also be an absolute path outside the collection. Its parent must exist. Use a destination the scheduled account can write to, and keep a recent copy on another drive or in approved backup storage. Archives are retained until you remove them.

Save your edits and close KB Forge. From the app checkout, test the command with your collection path:

```sh
python3 -m kbforge "/path/to/work-collection" --run-scheduled-backup
```

On Windows, you can use `py` instead of `python3` for this manual test. A successful first run prints the verified ZIP's path. Running it again before the interval is up prints “No scheduled backup is due.” Use the full path to the Python interpreter that runs KB Forge when configuring the scheduler. Set backups for times when the collection is idle. If the editor normally stays open, use its built-in scheduler so the backup can wait for in-app writes to finish.

## Windows · Task Scheduler

Open **Task Scheduler → Create Task**. Use your normal account with access to the collection and backup directory. On a workstation, **Run only when user is logged on** is a simple starting point.

| Setting | Example |
| --- | --- |
| Name | `KB Forge collection backup` |
| Trigger | Daily. In **Advanced settings**, repeat every **1 hour** for **1 day**. |
| Action | **Start a program** |
| Program/script | `C:\Users\Alex\dev\kb-forge\.venv\Scripts\python.exe` |
| Add arguments | `-m kbforge "C:\Users\Alex\KB\work-collection" --run-scheduled-backup` |
| Start in | `C:\Users\Alex\dev\kb-forge` |

Replace the example paths. To find your interpreter, run `py -c "import sys; print(sys.executable)"` or use the path to your virtual environment's Python. In the task's settings, choose **Do not start a new instance** if a scheduled run is already in progress. Save the task, right-click it and select **Run**, then check **Last Run Result** and the archive directory. [Microsoft Task Scheduler action documentation](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskaction?view=windowsserver2025-ps)

## macOS · launchd

Save the following as `~/Library/LaunchAgents/local.kbforge.backup.plist`. Create the `LaunchAgents` folder if needed. Replace all example paths. Use absolute paths in the plist, including the Python interpreter and the checkout in `WorkingDirectory`.

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

Validate, load, and test the job as the signed-in user:

```sh
plutil -lint "$HOME/Library/LaunchAgents/local.kbforge.backup.plist" &&
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.kbforge.backup.plist" &&
launchctl kickstart "gui/$(id -u)/local.kbforge.backup"
```

Check `~/Library/Logs/kbforge-backup.log` and the backup directory. The user agent runs in your login session. [Apple launchd job documentation](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

## Linux · cron

Use your user crontab on a system with cron installed and running. Run `crontab -e` and add this single line with your checkout, interpreter, collection, and log paths. The log's parent directory must already exist.

```cron
0 * * * * cd "/home/alex/dev/kb-forge" && "/home/alex/dev/kb-forge/.venv/bin/python" -m kbforge "/home/alex/KB/work-collection" --run-scheduled-backup >> "/home/alex/kbforge-backup.log" 2>&1
```

Confirm installation with `crontab -l`. Check the log and backup directory after the next hour. [Linux crontab format](https://www.man7.org/linux/man-pages/man5/crontab.5.html)

## Verify a restore

Extract a scheduled ZIP to a fresh folder. Open the extracted collection directory containing `kbforge.yaml` and check several articles and images. The [backup and restore guide](../README.md#back-up-and-restore-collections) also covers restoring one article.

If you use KB Forge v0.4.0, the same OS schedulers can run a short script that calls `--backup-collection --output` with a fresh timestamped ZIP path on each run. The built-in interval check and `--run-scheduled-backup` are available starting in v0.5.0.
