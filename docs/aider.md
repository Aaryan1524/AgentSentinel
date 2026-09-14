# Aider integration

Aider can invoke a custom command when it has finished responding and is
waiting for user input. Configure the Agent Sentinel bridge in Aider's YAML
configuration:

```yaml
notifications: true
notifications_command: "sentinel-aider-notify"
```

Or supply the equivalent command-line flag:

```bash
aider --notifications-command "sentinel-aider-notify"
```

The bridge records `needs_user_action`; Aider does not expose a reset timestamp
or a provider-neutral rate-limit event through this notification command.
