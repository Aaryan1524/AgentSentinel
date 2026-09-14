# Integration matrix

Agent Sentinel only calls an integration supported when its source can emit a
reproducible lifecycle event. Reset timing is always separate from event
detection.

| Agent | Integration | Finished / attention | Rate limit timing |
| --- | --- | --- | --- |
| Claude Code | Native command hooks | Supported | Five-hour `inferred` reset from first `UserPromptSubmit` |
| Gemini CLI | Native command hooks | Supported | Five-hour `inferred` reset from first `BeforeAgent` |
| Codex CLI | Sentinel launcher + `notify` | Completion and attention bridge | Five-hour `inferred` reset from first `sentinel-codex` invocation |
| Grok Build | Native command hooks | Supported | Five-hour `inferred` reset from first `UserPromptSubmit` |
| Other CLIs | Not in this release | Not advertised | Not advertised |

## Why the confidence rule matters

A notification can be valuable even when a provider never exposes its quota
reset. Sentinel emits a rate-limit event immediately. The scheduled reset is a
product estimate anchored to a reliable start event and is always marked
`inferred`, never provider-confirmed.
