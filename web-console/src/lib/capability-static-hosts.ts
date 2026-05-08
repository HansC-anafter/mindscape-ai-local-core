const staticHostCapabilityCodes = new Set([
  'blender_bridge',
  'brand_identity',
  'character_training',
  'chat_capture',
  'comfyui_runtime',
  'content_scheduler',
  'demo_aol_pack',
  'expert_network',
  'ig',
  'layer_asset_forge',
  'mindscape_cloud_integration',
  'multi_media_studio',
  'newsletter',
  'practice_companion',
  'public_persona_studio',
  'video_chapter_studio',
  'video_renderer',
  'web_generation',
  'world_asset_forge',
  'yogacoach',
]);

function capabilityCodeVariants(capabilityCode: string): string[] {
  const variants = new Set<string>();
  const trimmed = capabilityCode.trim();
  if (trimmed) {
    variants.add(trimmed);
    variants.add(trimmed.replace(/-/g, '_'));
    variants.add(trimmed.replace(/_/g, '-'));
  }
  return Array.from(variants);
}

function encodeSearchParams(searchParams?: Record<string, string | string[] | undefined>): string {
  if (!searchParams) {
    return '';
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
    } else if (typeof value === 'string') {
      params.set(key, value);
    }
  }

  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

export function resolveStaticCapabilityHostCode(capabilityCode: string): string | null {
  for (const variant of capabilityCodeVariants(capabilityCode)) {
    if (staticHostCapabilityCodes.has(variant)) {
      return variant;
    }
  }
  return null;
}

export function buildStaticCapabilityHostPath(
  workspaceId: string,
  capabilityCode: string,
  searchParams?: Record<string, string | string[] | undefined>,
): string | null {
  const hostCode = resolveStaticCapabilityHostCode(capabilityCode);
  if (!hostCode) {
    return null;
  }
  return `/workspaces/${encodeURIComponent(workspaceId)}/capability-ui-hosts/${hostCode}${encodeSearchParams(searchParams)}`;
}
