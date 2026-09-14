# Grok adapter

Grok Build supports command hooks for turn lifecycle, notifications, and
failures. Add this hook file at `~/.grok/hooks/agent-sentinel.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "sentinel-grok-hook"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "sentinel-grok-hook"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "sentinel-grok-hook"}]}],
    "StopFailure": [{
      "matcher": "rate_limit",
      "hooks": [{"type": "command", "command": "sentinel-grok-hook"}]
    }]
  }
}
```

`UserPromptSubmit` starts one five-hour inferred timer for the current Grok
usage window and queues it with QStash when configured. The adapter records
`Stop` and `idle_prompt` notifications as completion, `permission_prompt`
notifications as attention required, and a rate-limit `StopFailure` as an
immediate `rate_limited` alert. The hook contract does not establish an exact
provider reset timestamp, so the later reset remains `inferred`.
