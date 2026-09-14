# Codex adapter

Codex can invoke a user-level notification command and pass it a JSON payload.
Agent Sentinel accepts that payload through `sentinel-codex-notify`.

Add the following to the user-level `~/.codex/config.toml` after installing
Agent Sentinel:

```toml
notify = ["sentinel-codex-notify"]
```

Codex invokes `notify` after a turn, so it cannot establish the timer's start
by itself. Run Codex through Sentinel instead:

```bash
sentinel-codex
```

For a shell-level default, add `alias codex='sentinel-codex'` to your shell
configuration. The launcher records the first invocation in a five-hour
window, queues the QStash reset notification, then invokes the real `codex`
executable with the same arguments. Repeated invocations do not move the timer.

The exact notification fields can evolve with Codex releases. Sentinel treats a
generic notification as completion, maps clear permission/approval language to
`needs_user_action`, and maps clear rate-limit language to an immediate
`rate_limited` alert. Its later reset remains an `inferred` five-hour estimate,
never a provider-confirmed timestamp.

`sentinel init` does not edit TOML yet; it intentionally avoids a potentially
lossy configuration rewrite until TOML-preserving edits are available.
