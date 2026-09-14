# Codex adapter

Codex can invoke a user-level notification command and pass it a JSON payload.
Agent Sentinel accepts that payload through `sentinel-codex-notify`. Install
both the notification entry and an explicit zsh/bash launcher alias with:

```bash
sentinel init --adapter codex-cli --codex-alias --dry-run
sentinel init --adapter codex-cli --codex-alias
```

Restart the terminal afterwards. The installer adds
`notify = ["sentinel-codex-notify"]` to `~/.codex/config.toml` and a clearly
marked, removable `alias codex='sentinel-codex'` block to the active zsh or
bash profile. The launcher records the first invocation in a five-hour window,
queues the QStash reset notification, then invokes the real `codex` executable
with the same arguments. Repeated invocations do not move the timer.

If the TOML file already has a different `notify` command, or the shell profile
already aliases `codex`, Sentinel refuses to replace it. Use `sentinel-codex`
directly or resolve the existing customization first. `sentinel uninstall
--adapter codex-cli --codex-alias` removes only Sentinel's TOML line and
managed shell block.

The exact notification fields can evolve with Codex releases. Sentinel treats a
generic notification as completion, maps clear permission/approval language to
`needs_user_action`, and maps clear rate-limit language to an immediate
`rate_limited` alert. Its later reset remains an `inferred` five-hour estimate,
never a provider-confirmed timestamp.
