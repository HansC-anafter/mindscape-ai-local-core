# Export Layer Pack

## Purpose

Export layers and composition manifest for consumption by external tools such as Multi-Media Studio, video_renderer, or external editing software.

## When to Use

- After completing layer extraction and refinement workflow
- When preparing assets for Multi-Media Studio timeline integration
- For exporting to external editing tools (Photoshop, After Effects)
- When archiving a complete layer composition

## Inputs

- **job_run_id** (required): Job run ID containing the layers to export
- **output_format** (optional):
  - `png_layers`: PNG files with separate alpha (default)
  - `psd`: Photoshop document (future)
  - `ae_manifest`: After Effects compatible manifest (future)
- **include_metadata** (optional): Include full metadata in export (default: true)

## Process

1. **Load Job**: Retrieve job run and associated layer assets
2. **Package Layers**: Organize layer files according to format
3. **Generate Manifest**: Create composition_manifest.json
4. **Upload**: Store export pack to storage

## Outputs

- **export_pack_ref**: Reference to the exported pack (artifact_ref format)
- **layer_count**: Number of layers in the export

## Export Pack Structure

```
layer_asset_forge/jobs/{job_id}/exports/
├── layers/
│   ├── layer0.png
│   ├── layer1.png
│   └── ...
├── composition_manifest.json
└── job_run.json (if include_metadata=true)
```

## Example Usage

```yaml
inputs:
  job_run_id: "job_abc123"
  output_format: "png_layers"
  include_metadata: true
```

## Integration with MMS

The exported `composition_manifest.json` can be directly imported into Multi-Media Studio using `mms_import_laf_composition_manifest` playbook.

## Related Playbooks

- `laf_extract_layers`: Initial layer extraction
- `mms_import_laf_composition_manifest`: Import into MMS
- `vr_render_video`: Render final video from scene manifest
