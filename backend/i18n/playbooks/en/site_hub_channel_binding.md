# Site-Hub Channel Binding

## Goal
Bind a specific Site-Hub Channel to a Local-Core workspace.

## Steps

### 1. Get Available Channels

Use `site_hub_get_console_kit_channels` tool to retrieve available channels from Site-Hub:

```python
channels_result = await call_tool(
    "site_hub_get_console_kit_channels",
    {
        "runtime_id": "runtime_abc123",
        "agency": "openseo",  # Optional
        "tenant": "openseo",  # Optional
        "chainagent": "sinnie yoga",  # Optional
        "channel_type": "line"  # Optional
    }
)
```

**Note**: This tool requires the Runtime Environment to have OAuth2 authentication configured (Google OAuth).

### 2. Select Channel

If `channel_id` is provided, use that Channel directly.
Otherwise, select the first matching Channel from the retrieved Channels list.

### 3. Bind Channel

Use `site_hub_bind_channel` tool to bind the Channel to the Workspace:

```python
binding_result = await call_tool(
    "site_hub_bind_channel",
    {
        "workspace_id": "workspace_123",
        "runtime_id": "runtime_abc123",
        "channel_id": "channel_xyz789",
        "channel_type": "line",
        "channel_name": "LINE Channel",
        "agency": "openseo",
        "tenant": "openseo",
        "chainagent": "sinnie yoga",
        "binding_config": {
            "push_enabled": true,
            "notification_enabled": true
        }
    }
)
```

## Input Parameters

### Required Parameters
- `workspace_id`: Local-Core workspace ID
- `runtime_id`: Site-Hub Runtime Environment ID

### Optional Parameters
- `agency`: Agency name (for filtering)
- `tenant`: Tenant name (for filtering)
- `chainagent`: ChainAgent name (for filtering)
- `channel_type`: Channel type (for filtering, e.g., "line")
- `channel_id`: Directly specify Channel ID (skip selection step)
- `binding_config`: Binding configuration (push_enabled, notification_enabled, etc.)

## Outputs

- `binding_id`: Created binding ID
- `binding`: Complete binding information
- `channel`: Bound Channel information

## Error Handling

### OAuth2 Authentication Not Configured
- Ensure Runtime Environment's `auth_type` is "oauth2"
- Ensure `auth_config` contains valid OAuth2 token

### Channel Not Found
- Check if filter conditions are correct
- Verify that the Channel exists in Site-Hub

### Binding Failed
- Check if workspace_id is valid
- Ensure execution context has necessary permissions

## Completion

After binding is complete, the Channel will be available for use in the Workspace for:
- Pushing messages to the Channel
- Receiving messages from the Channel
- Other Channel-related features

