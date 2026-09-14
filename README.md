# Agent Sentinel

Agent Sentinel is an open-source, local-first reset notifier for developers
using Claude Code, Gemini CLI, Grok Build, and Codex CLI. It starts a
five-hour usage-window estimate from the first prompt and sends a Telegram
message when that window is expected to reset — even when the laptop is off.

The project deliberately separates a reported event from a predicted reset:

| Confidence | Meaning |
| --- | --- |
| `confirmed` | The CLI or provider supplied the reset timestamp. |
| `inferred` | Sentinel calculated it from a documented window and reliable event. |
| `unknown` | Sentinel knows the agent needs attention but does not claim a reset time. |

## Current status

The current build provides a durable SQLite store; Claude Code, Gemini CLI,
Grok Build, and Codex CLI adapters; Telegram delivery; QStash delayed delivery;
and safe hook configuration for Claude and Gemini. It does not require a
Sentinel cloud account or an AI-provider API token.

Every supported adapter starts a five-hour rolling-window estimate from a
reliable first-use signal. The reset alert is always marked **inferred**: the
CLI itself did not provide a reset timestamp. A rate-limit event also creates
an immediate alert, but never creates a duplicate reset message.

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

## Onboarding today

The current release safely connects every supported CLI. A user follows this
path:

1. Install Agent Sentinel in a Python 3.10+ environment.
2. Create a Telegram bot and identify the Telegram chat ID to receive alerts.
3. Create an Upstash QStash token for offline delayed delivery.
4. Put those three values in the private secrets file shown below.
5. Connect the AI CLI they use.
6. Run `sentinel doctor` to confirm the setup before their first prompt.

| CLI | Current connection step |
| --- | --- |
| Claude Code | Run `sentinel init --adapter claude-code` to back up and add its hooks; add `--dry-run` to preview. |
| Gemini CLI | Run `sentinel init --adapter gemini-cli` to back up and add its hooks; add `--dry-run` to preview. |
| Grok Build | Run `sentinel init --adapter grok-build` to create or merge its managed JSON hook file. |
| Codex CLI | Run `sentinel init --adapter codex-cli --codex-alias` to add `notify` and an explicit managed zsh/bash alias. |

For Claude and Gemini together, use:

```bash
sentinel init --detect --dry-run
sentinel init --detect
sentinel doctor
```

To include the optional Codex alias in a detected setup, add `--codex-alias`.
Open a new terminal after alias installation. The installer never overwrites an
existing configuration: it only adds missing Sentinel hooks and creates a
timestamped backup first. If Codex already has a different `notify` command or
shell alias, Sentinel refuses to replace it and reports the conflict instead.

### What happens after connection

On the first reliable prompt signal, Sentinel creates one five-hour inferred
usage window and immediately queues its reset notification with QStash. Later
prompts in that window do not move the timer. A rate-limit message creates an
immediate Telegram alert but does not create a duplicate reset alert.

## Offline delivery with QStash

For reset alerts while the computer is asleep or off, create an Upstash QStash
token and store these values in `~/.agent-sentinel/secrets.env` (or set
`AGENT_SENTINEL_SECRETS` to another file):

```dotenv
AGENT_SENTINEL_TELEGRAM_BOT_TOKEN=...
AGENT_SENTINEL_TELEGRAM_CHAT_ID=...
AGENT_SENTINEL_QSTASH_TOKEN=...
```

At the first prompt of a new window, Sentinel submits one deduplicated delayed
Telegram request to QStash for five hours later. QStash retries the delivery;
the original machine need not remain on. Sentinel keeps the local scheduler as
a fallback if QStash is not configured or cannot be reached when the window
starts. Keep this file private (`chmod 600 ~/.agent-sentinel/secrets.env`).

The no-server default sends QStash directly to Telegram; that destination URL
includes the Telegram bot token. Sentinel redacts the request body and headers
from QStash logs, but a user who needs stronger separation should set
`AGENT_SENTINEL_QSTASH_DESTINATION` to an HTTPS relay they control. The relay
must accept the form-encoded `chat_id` and `text` fields and forward them to
Telegram. A managed relay is an appropriate future Sentinel Cloud feature.

Each supported adapter also records events and immediately attempts Telegram
delivery for completion, attention, and rate-limit notifications; an
unavailable channel never blocks the originating agent.

Schedule a known future event locally with `sentinel schedule --id <event-id>
--at <ISO-8601 timestamp>`, then install the per-user fallback delivery runner
with `sentinel scheduler install`. It checks for due events once a minute on
macOS, Linux, and Windows. Each attempt and outcome is retained in local state and visible via
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

1. Smooth local onboarding: an interactive `sentinel init` flow that writes
   the secrets file and validates Telegram/QStash with user approval.
2. Optional Sentinel Cloud: managed delivery, phone push, multi-machine sync,
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
See [offline delivery setup](docs/local-scheduler.md) for QStash and local
fallback behavior.
