# Grok adapter

Grok Build supports command hooks for turn lifecycle, notifications, and
failures. Add this hook file at `~/.grok/hooks/agent-sentinel.json`:

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "sentinel-grok-hook"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "sentinel-grok-hook"}]}],
    "StopFailure": [{
      "matcher": "rate_limit",
      "hooks": [{"type": "command", "command": "sentinel-grok-hook"}]
    }]
  }
}
```

The adapter records `Stop` and `idle_prompt` notifications as completion,
`permission_prompt` notifications as attention required, and a rate-limit
`StopFailure` as `rate_limited`. Grok's hook contract does not establish a
reset timestamp, so its rate limits remain `unknown` timing.
