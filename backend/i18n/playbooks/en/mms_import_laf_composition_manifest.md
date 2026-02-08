## Import LAF Composition Manifest

This playbook reads `layer_asset_forge` `composition_manifest.json` and imports layers into an MMS `extension` track as timeline items (MVP: pinned at 0..0).

### Inputs

- `project_id` (MMS project)
- `composition_manifest_ref` (source: `url` / `file_path` / inline)

