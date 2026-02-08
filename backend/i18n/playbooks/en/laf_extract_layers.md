## Extract Layers (MVP)

This playbook provides a minimal Layer Asset Forge loop:

- Input an image (prefer referencing via `storage_key`)
- Output `composition_manifest.json` (with `storage_key` + accessible URL)

### Inputs

- `image_ref.storage_key` (preferred)
- or `image_ref.file_path` (local testing only; not recommended cross-pack)

### MVP Limitations

- No real segmentation/matte/inpaint yet; the whole image is exported as a single layer.
- Future versions will keep the same `artifact_ref / storage_key` contract and swap in real models.

