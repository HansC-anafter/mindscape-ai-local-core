# Refine Matte

## Purpose

Refine alpha matte for precise edge handling, especially for hair, transparency, and shadows. This playbook always creates a new version to maintain traceability in the derivation graph.

## When to Use

- After initial layer extraction when edges need refinement
- For elements with complex boundaries (hair, fur, feathers)
- When separating cast shadows from the main element
- For semi-transparent elements (glass, smoke, fabric)

## Inputs

- **element_asset_id** (required): ID of the element asset to refine
- **refine_options** (optional):
  - `hair_detail`: Enable detailed hair/fur edge refinement (default: true)
  - `separate_shadow`: Extract cast shadow as separate layer (default: false)
  - `transparency_aware`: Handle semi-transparent regions (default: false)

## Process

1. **Load Asset**: Retrieve element asset from storage
2. **Refine Matte**: Apply matting model (MODNet or similar) for edge refinement
3. **Shadow Separation**: Optionally extract shadow layer
4. **Register Version**: Create new asset version with derivation link

## Outputs

- **refined_asset_ref**: Reference to the refined element asset (new version)
- **shadow_layer_ref**: Reference to extracted shadow layer (if separate_shadow=true)

## Example Usage

```yaml
inputs:
  element_asset_id: "elem_abc123"
  refine_options:
    hair_detail: true
    separate_shadow: true
    transparency_aware: false
```

## Related Playbooks

- `laf_extract_layers`: Initial layer extraction
- `laf_complete_hidden`: Inpaint occluded regions
- `laf_export_pack`: Export refined layers
