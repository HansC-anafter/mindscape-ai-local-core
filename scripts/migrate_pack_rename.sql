-- Pack Rename Migration: site_hub_integration -> mindscape_cloud_integration
-- Also cleans legacy hyphenated pack_id: site-hub-integration
-- Run inside local-core PostgreSQL (docker compose exec -T postgres psql -U mindscape -d mindscape_core)

BEGIN;

-- 1. installed_packs: migrate old PK -> new PK (preserve metadata)
INSERT INTO installed_packs (pack_id, installed_at, enabled, metadata)
SELECT 'mindscape_cloud_integration', installed_at, enabled, metadata
FROM installed_packs
WHERE pack_id = 'site_hub_integration'
ON CONFLICT (pack_id) DO UPDATE SET
    installed_at = EXCLUDED.installed_at,
    enabled = EXCLUDED.enabled,
    metadata = EXCLUDED.metadata;

DELETE FROM installed_packs WHERE pack_id = 'site_hub_integration';

-- Clean legacy hyphenated version
DELETE FROM installed_packs WHERE pack_id = 'site-hub-integration';

-- 2. capability_ui_components (capability_code + component_id)
UPDATE capability_ui_components
SET capability_code = 'mindscape_cloud_integration'
WHERE capability_code IN ('site_hub_integration', 'site-hub-integration');

UPDATE capability_ui_components
SET component_id = 'MindscapeCloudChannelBindingPanel'
WHERE component_id = 'SiteHubChannelBindingPanel';

-- 3. tool_registry (conditional: update if rows exist)
UPDATE tool_registry
SET capability_code = REPLACE(capability_code, 'site_hub_integration', 'mindscape_cloud_integration')
WHERE capability_code LIKE 'site_hub_integration%';

UPDATE tool_registry
SET origin_capability_id = REPLACE(origin_capability_id, 'site_hub_integration', 'mindscape_cloud_integration')
WHERE origin_capability_id LIKE 'site_hub_integration%';

COMMIT;
