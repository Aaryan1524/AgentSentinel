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

The current local-first build provides the portable event contract, a durable
SQLite store, Claude Code, Gemini CLI, Codex, and Grok adapters, Telegram
delivery, a local scheduler, and safe hook configuration for Claude and Gemini.
No cloud account or provider token is needed for the core.

For Claude Code, Sentinel also restores the local five-hour rolling-window
behavior: the first observed prompt starts an **inferred** window, a rate-limit
hook alerts immediately, and Sentinel durably schedules a later
`reset_available` notification. It never describes this inferred time as a
provider-confirmed reset.

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

For automatic adapter notifications, place those same values in
`~/.agent-sentinel/secrets.env` (or set `AGENT_SENTINEL_SECRETS` to another
file). Each supported adapter records a new event and immediately attempts
Telegram delivery; an unavailable channel never blocks the originating agent.

Schedule a known future event locally with `sentinel schedule --id <event-id>
--at <ISO-8601 timestamp>`, then install the per-user delivery runner with
`sentinel scheduler install`. It checks for due events once a minute on macOS
and Linux. Each attempt and outcome is retained in local state and visible via
`sentinel deliveries --json`; failed delivery remains pending for retry.
The installer resolves the currently installed `sentinel` executable; pass
`--executable /absolute/path/to/sentinel` when using a nonstandard environment.

Use `sentinel doctor` to check the local state path, configured adapters,
Telegram credentials, and scheduler without sending a notification.

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

1. Optional Sentinel Cloud: managed delivery, phone push, multi-machine sync,
   history, and team policies.

The local CLI will remain useful without Sentinel Cloud.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Public CI verifies the test suite on Python 3.10 through 3.13.

Licensed under [Apache-2.0](LICENSE).

See [Claude Code adapter setup](docs/claude-code.md) for the current hook map.
See [Gemini CLI adapter setup](docs/gemini-cli.md) for its supported events.
See [Codex setup](docs/codex.md), [Grok setup](docs/grok.md), and the full
[integration matrix](docs/integration-matrix.md) for adapter support status.
See [local scheduler setup](docs/local-scheduler.md) for durable reset delivery.
OpenCode and Aider setup are available in [the OpenCode guide](docs/opencode.md)
and [the Aider guide](docs/aider.md).
