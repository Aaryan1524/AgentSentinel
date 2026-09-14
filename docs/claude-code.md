# Claude Code adapter

The adapter translates Claude Code lifecycle hooks into Agent Sentinel events.
It is observational: it writes no hook output and always exits successfully, so
Sentinel never blocks a prompt, a permission decision, or an agent stop.

## Events

| Claude Code hook | Agent Sentinel event |
| --- | --- |
| `Stop` | `agent_finished` |
| `PermissionRequest` | `needs_user_action` |
| `Notification` | `needs_user_action` |
| `StopFailure` matched to `rate_limit` | `rate_limited` with `unknown` reset confidence |

Claude Code documents that `StopFailure` identifies a rate-limit error, but it
does not document a reset timestamp in that hook payload. Sentinel therefore
does not infer one yet.

## Hook configuration

Install Agent Sentinel in an environment available to Claude Code, then add
the command entries below to the `hooks` section of the relevant Claude Code
settings file. Merge these entries with existing hooks; do not overwrite the
file.

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "sentinel-claude-hook"}]}],
    "PermissionRequest": [{"hooks": [{"type": "command", "command": "sentinel-claude-hook"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "sentinel-claude-hook"}]}],
    "StopFailure": [{
      "matcher": "rate_limit",
      "hooks": [{"type": "command", "command": "sentinel-claude-hook"}]
    }]
  }
}
```

Until the installer lands, `sentinel-claude-hook` is the package command that
runs the adapter. The installer will patch settings safely with backups.
