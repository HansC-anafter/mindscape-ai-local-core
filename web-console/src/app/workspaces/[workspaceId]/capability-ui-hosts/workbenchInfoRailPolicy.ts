import type { CapabilityWorkbenchInfoMetadata } from '@/types/capability-workbench';

const ACTIONABLE_TONES = new Set(['warning', 'danger']);
const ACTIONABLE_STATUS_PATTERN = /\b(blocked|required|requires|missing|needs[_\s-]*setup|failed|error|warning|review)\b/i;

export function shouldExposeWorkbenchInfoRail(
  metadata: CapabilityWorkbenchInfoMetadata | null,
): metadata is CapabilityWorkbenchInfoMetadata {
  if (!metadata) {
    return false;
  }

  if (metadata.session?.status === 'failed') {
    return true;
  }

  return metadata.status.some((status) => (
    ACTIONABLE_TONES.has(status.tone) ||
    ACTIONABLE_STATUS_PATTERN.test(`${status.key} ${status.label} ${status.value}`)
  ));
}
