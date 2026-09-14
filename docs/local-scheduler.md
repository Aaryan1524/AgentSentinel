# Local scheduler

QStash is the preferred offline delivery path: the first-prompt hook sends a
one-time delayed Telegram request to QStash, which delivers it even if the
computer is off. The local scheduler is the fallback when QStash is not
configured or cannot be reached at window start.

Install the per-user fallback runner after you configure Telegram:

```bash
sentinel scheduler install
sentinel scheduler status
```

On macOS, Sentinel writes and activates a `launchd` LaunchAgent. On Linux, it
writes and enables a user `systemd` service and timer. On Windows, it creates a
per-user Task Scheduler task. All run `sentinel run-due` once per minute. The
command resolves the active `sentinel` executable;
provide `--executable /absolute/path/to/sentinel` when your installation uses a
nonstandard environment.

Preview first with `sentinel scheduler install --dry-run`. Existing Sentinel
scheduler files are backed up before replacement. To remove only the files
owned by Sentinel, use:

```bash
sentinel scheduler uninstall
```
