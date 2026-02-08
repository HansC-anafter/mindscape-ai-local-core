# Site-Hub Runtime Environment Setup

## Goal
Guide user through Site-Hub runtime environment discovery, validation, and registration.

## Steps

### 1. Check Environment Variable

First check if `SITE_HUB_API_BASE` environment variable is set.

If not set, prompt user:
- Please set `SITE_HUB_API_BASE` environment variable to Site-Hub API base URL
- Example: `export SITE_HUB_API_BASE=http://localhost:8102`

### 2. Discover Site-Hub

Use `site_hub_discover_runtime` tool to discover and validate Site-Hub connection:

```python
discovery_result = await call_tool(
    "site_hub_discover_runtime",
    {
        "site_hub_base_url": None  # Optional, will auto-detect from SITE_HUB_API_BASE
    }
)
```

If discovery fails:
- Check if Site-Hub is running
- Check if URL is correct
- Check network connectivity

### 3. Register Runtime

If discovery succeeds, use `site_hub_register_runtime` tool to register:

```python
if discovery_result.get("success"):
    register_result = await call_tool(
        "site_hub_register_runtime",
        {
            "site_hub_base_url": discovery_result.get("site_hub_url"),
            "runtime_name": "Site-Hub"  # Optional, defaults to "Site-Hub"
        }
    )
```

### 4. Verify Setup

After registration, verify runtime is available:

- Check returned `runtime_id`
- Confirm status is "active"
- Optional: Use `site_hub_list_channels` tool to list available channels

## Error Handling

### Environment Variable Not Set
- Prompt user to set `SITE_HUB_API_BASE`
- Provide setup example

### Connection Failed
- Check if Site-Hub service is running
- Check if URL is correct
- Check firewall/network settings

### Authentication Failed
- Confirm execution_context is available
- Check user permissions

### URL Validation Failed
- Check if URL is in allowlist
- Contact administrator to add URL to allowlist

## Completion

After setup, Site-Hub will be available as runtime environment for:
- Dispatch Workspace
- Cell Workspace
- Other features requiring Site-Hub

