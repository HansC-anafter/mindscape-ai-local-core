# Validate Manifest

## Purpose

Validate scene_edit_manifest structure and asset accessibility without performing actual rendering. Use this for pre-flight checks before committing to a render job.

## When to Use

- Before submitting a render job
- To diagnose rendering issues
- For automated pipeline validation

## Inputs

- **manifest_ref** (required): Reference to scene_edit_manifest
- **check_assets** (optional): Whether to verify asset accessibility - default: true

## Outputs

- **valid**: Whether manifest is valid for rendering
- **errors**: List of validation errors (blocking)
- **warnings**: List of warnings (non-blocking)
- **asset_checks**: Individual asset accessibility results

## Example Usage

```yaml
inputs:
  manifest_ref:
    storage_key: "multi_media_studio/projects/proj_123/scene_edit_manifest.json"
  check_assets: true
```

## Related Playbooks

- `vr_render_video`: Full rendering workflow
