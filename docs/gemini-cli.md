# Gemini CLI adapter

Agent Sentinel uses Gemini CLI command hooks as an observational adapter. It
prints no output and exits successfully, so it does not modify the agent loop.

## Events

| Gemini CLI hook | Agent Sentinel event |
| --- | --- |
| `BeforeAgent` | Starts a five-hour inferred reset timer; no immediate notification |
| `AfterAgent` | `agent_finished` |
| `Notification` | `needs_user_action` |
| `Notification` whose message says rate limit | Immediate `rate_limited`; the existing reset timer remains `inferred` |

Gemini CLI's hook schema does not provide a provider reset timestamp. Sentinel
therefore starts the product's five-hour estimate at `BeforeAgent`, marks the
later reset delivery as `inferred`, and never describes it as exact.

## Hook configuration

Merge the following entries into `.gemini/settings.json` or the applicable
Gemini CLI settings file. Do not overwrite existing hooks.

```json
{
  "hooks": {
    "BeforeAgent": [{
      "matcher": "*",
      "hooks": [{"type": "command", "command": "sentinel-gemini-hook"}]
    }],
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

`sentinel init --adapter gemini-cli` safely adds the complete hook set with a
timestamped backup. Configure QStash as described in the main README for the
timer to survive an offline computer.
