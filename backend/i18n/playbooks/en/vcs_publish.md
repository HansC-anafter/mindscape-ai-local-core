# Publish Project

Export final asset bundle with manifest for a completed project.

## Objective

Generate and export the final manifest and asset bundle for a Video Chapter Studio project, making it ready for consumption by downstream systems.

## Input Requirements

- **project_id**: Project ID to publish
- **output_format** (optional): Manifest format (`json` or `yaml`, default: json)
- **include_assets** (optional): Include asset files in bundle (default: true)
- **publish_options** (optional): Publishing configuration
  - `storage_target`: Target storage location
  - `version_tag`: Version tag for the bundle
  - `mark_as_final`: Mark project as finalized

## Process Flow

1. **Validate Project**: Ensure project is ready for publishing
2. **Run Extension Hooks**: Execute domain extension `on_publish` hooks
3. **Generate Manifest**: Create manifest file with all chapter data
4. **Upload Bundle**: Upload assets and manifest to storage
5. **Update Status**: Mark project as published

## Output

- **bundle_id**: Unique bundle identifier
- **manifest_url**: URL to the manifest file
- **asset_urls**: URLs to all included assets
- **status**: Publishing status

## Output Bundle Structure

```
bundle/
├── manifest.json
├── chapters/
│   ├── chapter_1.json
│   ├── chapter_2.json
│   └── ...
├── thumbnails/
│   ├── chapter_1_start.jpg
│   ├── chapter_1_middle.jpg
│   └── ...
└── metadata/
    ├── quality_report.json
    └── extension_data.json
```

## Notes

- Extension hooks can add domain-specific data to the manifest
- Published bundles can be referenced by external systems
- Version tags enable multiple versions of the same project


