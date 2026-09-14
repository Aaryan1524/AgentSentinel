# Integration matrix

Agent Sentinel only calls an integration supported when its source can emit a
reproducible lifecycle event. Reset timing is always separate from event
detection.

| Agent | Integration | Finished / attention | Rate limit timing |
| --- | --- | --- | --- |
| Claude Code | Native command hooks | Supported | `unknown` until a documented timestamp is available |
| Gemini CLI | Native command hooks | Supported | `unknown` |
| Codex CLI | User-level `notify` command | Completion and attention bridge | `unknown` |
| Grok Build | Native command hooks | Supported | `unknown` |
| OpenCode | Plugin event surface | Plugin template planned | Provider-dependent; do not predict |
| Aider | Custom notification command | External command bridge planned | Not exposed |
| Cursor, Cline, Windsurf | Research required | Do not advertise as supported yet | Not exposed |

## Why the confidence rule matters

A notification can be valuable even when a provider never exposes its quota
reset. Sentinel emits a rate-limit event immediately, but only includes a
timestamp when the provider supplies it or a documented rolling window can be
anchored to a reliable start event.
