/**
 * Copy to .opencode/plugins/agent-sentinel.js in a project using OpenCode.
 * It deliberately sends only minimal metadata to the local Sentinel CLI.
 */
export const AgentSentinelPlugin = async ({ $ }) => ({
  event: async ({ event }) => {
    let kind;
    if (event.type === "session.idle") kind = "agent_finished";
    else if (event.type === "permission.asked") kind = "needs_user_action";
    else if (event.type === "session.error") {
      const detail = JSON.stringify(event.properties ?? {}).toLowerCase();
      kind = detail.includes("rate limit") ? "rate_limited" : "needs_user_action";
    } else return;

    await $`sentinel emit --agent opencode --kind ${kind} --metadata ${JSON.stringify({ event_type: event.type })}`;
  },
});
