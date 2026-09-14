# Claude Code adapter

The adapter translates Claude Code lifecycle hooks into Agent Sentinel events.
It is observational: it writes no hook output and always exits successfully, so
Sentinel never blocks a prompt, a permission decision, or an agent stop.

## Events

| Claude Code hook | Agent Sentinel event |
| --- | --- |
| `UserPromptSubmit` | Starts a local Claude rolling-window estimate; no notification |
| `Stop` | `agent_finished` |
| `PermissionRequest` | `needs_user_action` |
| `Notification` | `needs_user_action` |
| `StopFailure` matched to `rate_limit` | `rate_limited`, then scheduled `reset_available` |

Claude Code's rate-limit hook does not provide a reset timestamp. Sentinel
therefore treats a reset as an **inference**, never a provider-confirmed fact:
it records the first `UserPromptSubmit` it observes in a five-hour rolling
window, retains that window across hook processes, and calculates the reset
from that start. Every additional prompt in the active window leaves the
estimate unchanged. When `StopFailure` reports `rate_limit`, Sentinel notifies
immediately and creates a durable `reset_available` delivery for that inferred
time. If Sentinel has no active locally observed window, it only sends the
rate-limit alert with `unknown` timing.

When QStash is configured, the `UserPromptSubmit` hook queues the reset alert
off-device immediately, so it can arrive when this machine is off. Run
`sentinel scheduler install` to retain a local fallback on macOS, Linux, or
Windows when QStash is unavailable.

## Hook configuration

Install Agent Sentinel in an environment available to Claude Code, then add
the command entries below to the `hooks` section of the relevant Claude Code
settings file. Merge these entries with existing hooks; do not overwrite the
file.

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "sentinel-claude-hook"}]}],
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

`sentinel init --adapter claude-code` safely adds the complete hook set with a
timestamped backup. `sentinel-claude-hook` is the package command the adapter
runs.
