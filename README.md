# Agent Sentinel

Agent Sentinel notifies you when an AI coding agent finishes work, needs an
approval, hits a limit, or becomes available again. It is an open-source,
local-first foundation for Claude Code, Gemini CLI, OpenCode, Codex, Aider,
and other agent CLIs.

The project deliberately separates a reported event from a predicted reset:

| Confidence | Meaning |
| --- | --- |
| `confirmed` | The CLI or provider supplied the reset timestamp. |
| `inferred` | Sentinel calculated it from a documented window and reliable event. |
| `unknown` | Sentinel knows the agent needs attention but does not claim a reset time. |

## Current status

The first runnable slice provides the portable event contract, a durable local
SQLite store, a Python CLI, Claude Code and Gemini CLI hook adapters, and an
opt-in Telegram delivery command. Schedulers and safe installers are next; no
cloud account or provider token is needed for the core.

## Try the core

Requires Python 3.10+.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

sentinel emit \
  --agent claude-code \
  --kind rate_limited \
  --id example-limit-001 \
  --reset-at 2026-09-14T17:00:00Z \
  --confidence confirmed

sentinel status --json
```

To send a recorded event to Telegram, set `AGENT_SENTINEL_TELEGRAM_BOT_TOKEN`
and `AGENT_SENTINEL_TELEGRAM_CHAT_ID`, then run `sentinel notify --id <event-id>`.
Use `--dry-run` to preview the notification without credentials or network use.

Schedule a known future event locally with `sentinel schedule --id <event-id>
--at <ISO-8601 timestamp>`, then run `sentinel run-due` from your platform's
scheduler. Each attempt and outcome is retained in local state and visible via
`sentinel deliveries --json`; failed delivery remains pending for retry.

## Safe hook setup

Run `sentinel init --detect --dry-run` to preview configuration for detected
Claude Code and Gemini CLI settings. Remove `--dry-run` to apply only the
missing Agent Sentinel hook groups. Existing configuration is preserved and a
timestamped backup is written beside each changed settings file.

Run `sentinel uninstall --detect --dry-run` to preview removal. The real
command removes only Agent Sentinel commands, retains other hooks in the same
group, and creates another timestamped backup before it writes.

Runtime state defaults to `~/.agent-sentinel/state.sqlite3`. Set
`AGENT_SENTINEL_STATE` to use another path, for example in tests or a managed
installation.

## Event contract

Every adapter emits one of:

- `agent_finished`
- `needs_user_action`
- `rate_limited`
- `reset_available`

Adapters should reuse a stable source event ID when available. The core uses
that ID to make repeated hook delivery safe and idempotent.

## Roadmap

1. Platform scheduler installation and `doctor` workflows for
   macOS, Linux, and Windows.
2. Optional Sentinel Cloud: managed delivery, phone push, multi-machine sync,
   history, and team policies.

The local CLI will remain useful without Sentinel Cloud.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Licensed under [Apache-2.0](LICENSE).

See [Claude Code adapter setup](docs/claude-code.md) for the current hook map.
See [Gemini CLI adapter setup](docs/gemini-cli.md) for its supported events.
