import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

function normalizeSegment(value: string | null | undefined, fallback: string): string {
  const normalized = (value || fallback)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

export function buildRemoteWorkbenchMeetingId({
  workspaceId,
  targetCapabilityCode,
}: {
  workspaceId: string;
  targetCapabilityCode: string | null;
}): string {
  const capabilitySegment = normalizeSegment(targetCapabilityCode, 'all-packs');
  return `remote-workbench:${workspaceId}:${capabilitySegment}`;
}

export function buildRemoteWorkbenchGraphAnchor({
  workspaceId,
  targetCapabilityCode,
  targetCapabilityLabel,
}: {
  workspaceId: string;
  targetCapabilityCode: string | null;
  targetCapabilityLabel: string | null;
}): AddressableObjectRef | null {
  if (!targetCapabilityCode) {
    return null;
  }

  return {
    uri: `aol://workspace/${encodeURIComponent(workspaceId)}/capability/${encodeURIComponent(targetCapabilityCode)}`,
    owner_pack: targetCapabilityCode,
    object_kind: 'capability_runtime_entry',
    object_id: targetCapabilityCode,
    workspace_id: workspaceId,
    selector: {
      source: 'remote_workbench_runtime_entry',
      target_capability: targetCapabilityCode,
      label: targetCapabilityLabel,
    },
    source_surface: 'remote_workbench_runtime_entry',
  };
}
