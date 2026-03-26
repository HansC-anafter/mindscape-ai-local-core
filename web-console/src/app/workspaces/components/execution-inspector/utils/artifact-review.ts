import type { VisualAcceptanceBundleContent } from '../types/execution';

export interface FollowupActionOption {
  id: string;
  label: string;
  description: string;
}

function canonicalFollowupActionId(actionId: string): string {
  return actionId;
}

export const FOLLOWUP_ACTION_OPTIONS: FollowupActionOption[] = [
  {
    id: 'compare_against_accepted_baseline',
    label: 'Compare Accepted Baseline',
    description: 'Review the current bundle against the latest accepted baseline before deciding on the next step.',
  },
  {
    id: 'rerender_same_preset',
    label: 'Rerender Same Preset',
    description: 'Keep the current preset and lane, then run another rerender to verify whether the adjustment works.',
  },
  {
    id: 'retune_prompt_and_negative',
    label: 'Retune Prompt / Negative',
    description: 'Prioritize fixes to prompt, negative prompt, composition, or semantic-following issues.',
  },
  {
    id: 'retune_character_adapter',
    label: 'Retune Adapter / LoRA',
    description: 'Adjust character adapter, LoRA strength, or hybrid binding parameters.',
  },
  {
    id: 'rebuild_contact_zone_mask',
    label: 'Rebuild Contact-Zone Mask',
    description: 'Go back to the object isolation, mask, and alpha path to fix contact-zone and edge issues.',
  },
  {
    id: 'escalate_local_scene_review',
    label: 'Escalate Local-Scene Review',
    description: 'When the quality gate is escalated, hand the follow-up over to the local-scene or manual lane.',
  },
  {
    id: 'capture_accepted_baseline',
    label: 'Capture Accepted Baseline',
    description: 'Use this result as a baseline candidate for future comparisons within the same package or preset.',
  },
  {
    id: 'pack_consumer_handoff',
    label: 'Handoff To Pack Consumer',
    description: 'When the output is acceptable, hand this review evidence to the pack-owned consumer for downstream processing.',
  },
];

const FOLLOWUP_ACTION_IDS = new Set(FOLLOWUP_ACTION_OPTIONS.map((option) => option.id));

function uniqueActionIds(values: Iterable<string>): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    ordered.push(value);
  }
  return ordered;
}

export function normalizeFollowupActions(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return uniqueActionIds(
    value
      .map((item) => canonicalFollowupActionId(String(item || '').trim()))
      .filter((item) => item && FOLLOWUP_ACTION_IDS.has(item)),
  );
}

export function followupActionLabel(actionId: string): string {
  const normalizedActionId = canonicalFollowupActionId(actionId);
  return (
    FOLLOWUP_ACTION_OPTIONS.find((option) => option.id === normalizedActionId)?.label ||
    normalizedActionId
  );
}

export function followupActionDescription(actionId: string): string {
  const normalizedActionId = canonicalFollowupActionId(actionId);
  return (
    FOLLOWUP_ACTION_OPTIONS.find((option) => option.id === normalizedActionId)?.description || ''
  );
}

export function buildSuggestedFollowupActions(
  content: VisualAcceptanceBundleContent | null | undefined,
  options?: {
    hasAcceptedBaseline?: boolean;
  },
): string[] {
  const sourceKind = String(content?.source_kind || '').trim().toLowerCase();
  const bindingMode = String(content?.binding_mode || '').trim().toLowerCase();
  const qualityGateState = String(
    content?.object_workload_snapshot?.quality_gate_state || '',
  )
    .trim()
    .toLowerCase();
  const artifactIds = Array.isArray(content?.artifact_ids) ? content.artifact_ids : [];

  const next: string[] = [];

  if (options?.hasAcceptedBaseline) {
    next.push('compare_against_accepted_baseline');
  }

  if (sourceKind === 'laf_patch') {
    next.push('rebuild_contact_zone_mask', 'rerender_same_preset');
  } else if (sourceKind === 'vr_render' || sourceKind === 'character_training_eval') {
    next.push('rerender_same_preset', 'retune_prompt_and_negative');
  }

  if (bindingMode === 'adapter_only' || bindingMode === 'hybrid' || artifactIds.length > 0) {
    next.push('retune_character_adapter');
  }

  if (qualityGateState === 'manual_required' || qualityGateState === 'escalate_local_scene') {
    next.push('escalate_local_scene_review');
  }

  if (content?.package_id && !options?.hasAcceptedBaseline) {
    next.push('capture_accepted_baseline');
  }

  if (!next.length) {
    next.push('rerender_same_preset');
  }

  return uniqueActionIds(next).slice(0, 4);
}
