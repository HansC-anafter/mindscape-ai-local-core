# Complete Hidden Regions

## Purpose

Inpaint occluded regions to complete hidden parts of elements. This playbook ALWAYS creates a new version to ensure traceability - the original asset is never modified.

## When to Use

- When an element is partially occluded by another object
- For background completion behind removed objects
- When preparing assets for flexible repositioning
- For creating "complete" versions of cropped elements

## Inputs

- **element_asset_id** (required): ID of the element asset to complete
- **mask_region** (required): Region specification for inpainting
  - Can be auto-detected from occlusion analysis or manually specified
- **strategy** (optional):
  - `conservative`: Minimal inpainting, preserve original as much as possible
  - `aggressive`: More extensive completion for better visual result

## Process

1. **Load Asset**: Retrieve element asset and mask region
2. **Inpaint**: Apply inpainting model (LaMa or similar) to complete hidden regions
3. **Quality Check**: Calculate completion confidence score
4. **Register Version**: Create new asset version with derivation link

## Outputs

- **completed_asset_ref**: Reference to the completed element asset (new version)
- **completion_confidence**: Confidence score (0.0-1.0) for the inpainted region

## Example Usage

```yaml
inputs:
  element_asset_id: "elem_abc123"
  mask_region:
    x: 100
    y: 50
    width: 200
    height: 150
    source: "occlusion_detection"
  strategy: "conservative"
```

## Important Notes

- Inpainting always produces a NEW version - the original is preserved
- Use derivation graph to trace back to the original asset
- Lower confidence scores may indicate need for manual review

## Related Playbooks

- `laf_extract_layers`: Initial layer extraction
- `laf_refine_matte`: Edge refinement before/after completion
- `laf_version_and_register`: Manual version control
