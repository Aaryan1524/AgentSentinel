# Local scheduler

Scheduled reset alerts stay on the machine. Install the per-user runner after
you configure a delivery channel:

```bash
sentinel scheduler install
sentinel scheduler status
```

On macOS, Sentinel writes and activates a `launchd` LaunchAgent. On Linux, it
writes and enables a user `systemd` service and timer. Both run `sentinel
run-due` once per minute. The command resolves the active `sentinel` executable;
provide `--executable /absolute/path/to/sentinel` when your installation uses a
nonstandard environment.

Preview first with `sentinel scheduler install --dry-run`. Existing Sentinel
scheduler files are backed up before replacement. To remove only the files
owned by Sentinel, use:

```bash
sentinel scheduler uninstall
```

Windows scheduler installation is not included yet. You can still run
`sentinel run-due` from Task Scheduler until that adapter is added.
