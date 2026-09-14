# Gemini CLI adapter

Agent Sentinel uses Gemini CLI command hooks as an observational adapter. It
prints no output and exits successfully, so it does not modify the agent loop.

## Events

| Gemini CLI hook | Agent Sentinel event |
| --- | --- |
| `AfterAgent` | `agent_finished` |
| `Notification` | `needs_user_action` |
| `Notification` whose message says rate limit | `rate_limited` with `unknown` reset confidence |

Gemini CLI's documented hook schema supplies lifecycle and notification data,
but does not promise a quota reset timestamp. Sentinel records a detected
rate-limit notification immediately and deliberately makes no reset prediction.

## Hook configuration

Merge the following entries into `.gemini/settings.json` or the applicable
Gemini CLI settings file. Do not overwrite existing hooks.

```json
{
  "hooks": {
    "AfterAgent": [{
      "matcher": "*",
      "hooks": [{"type": "command", "command": "sentinel-gemini-hook"}]
    }],
    "Notification": [{
      "matcher": "*",
      "hooks": [{"type": "command", "command": "sentinel-gemini-hook"}]
    }]
  }
}
```

The current installer has not landed yet. `sentinel-gemini-hook` is provided
by the installed package; the future installer will safely merge this setup
and retain a backup of user configuration.
