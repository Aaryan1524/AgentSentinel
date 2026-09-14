# OpenCode integration

OpenCode plugins expose session, permission, and error events. Copy
[`plugins/opencode/agent-sentinel.js`](../plugins/opencode/agent-sentinel.js)
to `.opencode/plugins/agent-sentinel.js` in a project, then restart OpenCode.

The plugin records:

- `session.idle` as `agent_finished`
- `permission.asked` as `needs_user_action`
- `session.error` as `rate_limited` only when its event details explicitly say
  rate limit; otherwise it reports attention required

OpenCode's provider is variable, so the plugin never predicts a quota reset.
