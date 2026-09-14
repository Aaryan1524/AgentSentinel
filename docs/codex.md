# Codex adapter

Codex can invoke a user-level notification command and pass it a JSON payload.
Agent Sentinel accepts that payload through `sentinel-codex-notify`.

Add the following to the user-level `~/.codex/config.toml` after installing
Agent Sentinel:

```toml
notify = ["sentinel-codex-notify"]
```

The exact notification fields can evolve with Codex releases. Sentinel treats a
generic notification as completion, maps clear permission/approval language to
`needs_user_action`, and maps clear rate-limit language to `rate_limited` with
`unknown` reset confidence. It never predicts a Codex reset time.

`sentinel init` does not edit TOML yet; it intentionally avoids a potentially
lossy configuration rewrite until TOML-preserving edits are available.
