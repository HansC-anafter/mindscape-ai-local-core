import { describe, expect, it } from 'vitest';

import {
  getMeetingFocusRole,
  getMeetingMissingContext,
  getMeetingNextStepNodeId,
  getMeetingNextStepTitle,
  getMeetingRuntimeLabel,
  getMeetingWorkStatus,
} from './meetingWorkbenchStatus';
import type {
  AddressableObjectRef,
  AddressableObjectSummary,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import type { MeetingNode, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';

const baseNode: MeetingNode = {
  id: 'node',
  title: 'Node',
  eyebrow: 'Node',
  detail: 'detail',
  status: 'ready',
  kind: 'group',
  lane: 'context',
};

function runtimeSnapshot(overrides: Partial<RuntimeInspectorSnapshot> = {}): RuntimeInspectorSnapshot {
  return {
    resolvedRuntime: null,
    dispatchChain: [],
    boundRuntimeIds: [],
    agents: [],
    loading: false,
    error: null,
    ...overrides,
  };
}

const sourceRef: AddressableObjectRef = {
  uri: 'mindscape://ig/reference/ref_global',
  owner_pack: 'ig',
  object_kind: 'reference',
  object_id: 'ref_global',
};

const targetRef: AddressableObjectRef = {
  uri: 'mindscape://fixture_pack/generic_object/object_open',
  owner_pack: 'fixture_pack',
  object_kind: 'generic_object',
  object_id: 'object_open',
};

const sourceSummary: AddressableObjectSummary = {
  ref: sourceRef,
  title: 'Global Reference',
  labels: [],
};

function attachResponse(overrides: Partial<ObjectMeetingAttachResponse> = {}): ObjectMeetingAttachResponse {
  return {
    workspace_id: 'ws-global',
    meeting_id: 'mtg-global',
    status: 'attached',
    attachments: [],
    staged_refs: [],
    review_routes: [],
    errors: [],
    ...overrides,
  };
}

describe('meetingWorkbenchStatus', () => {
  it('derives product work status without treating loading placeholders as runtime runs', () => {
    expect(
      getMeetingWorkStatus([
        { ...baseNode, id: 'execution-graph-state', status: 'running', lane: 'runs' },
      ], ''),
    ).toBe('Ready');
    expect(
      getMeetingWorkStatus([
        { ...baseNode, id: 'run-1', status: 'running', kind: 'run', lane: 'runs' },
      ], ''),
    ).toBe('Running');
    expect(getMeetingWorkStatus([{ ...baseNode, status: 'blocked' }], '')).toBe('Blocked');
    expect(getMeetingWorkStatus([{ ...baseNode, kind: 'artifact', lane: 'artifacts' }], '')).toBe('Outcome ready');
    expect(getMeetingWorkStatus([baseNode], 'Draft an instruction')).toBe('Drafting');
  });

  it('derives next-step and runtime labels for the Work view context bar', () => {
    expect(getMeetingNextStepTitle([{ ...baseNode, lane: 'next', title: 'Review output' }])).toBe('Review output');
    expect(getMeetingNextStepTitle([baseNode])).toBe('Ready for instruction');
    expect(getMeetingNextStepNodeId([{ ...baseNode, id: 'next-1', lane: 'next' }])).toBe('next-1');
    expect(getMeetingNextStepNodeId([{ ...baseNode, id: 'blocked-1', status: 'blocked' }])).toBe('blocked-1');
    expect(getMeetingNextStepNodeId([{ ...baseNode, id: 'guidance-1', metadata: { guidance_id: 'card-1' } }])).toBe('guidance-1');
    expect(getMeetingNextStepNodeId([baseNode])).toBeNull();
    expect(getMeetingRuntimeLabel(runtimeSnapshot({ loading: true }))).toBe('Runtime...');
    expect(getMeetingRuntimeLabel(runtimeSnapshot({ resolvedRuntime: 'local-executor' }))).toBe('local-executor');
    expect(getMeetingRuntimeLabel(runtimeSnapshot({ dispatchChain: ['default-chain'] }))).toBe('default-chain');
  });

  it('derives focus role and missing context for the Work view context bar', () => {
    expect(getMeetingFocusRole(sourceSummary, attachResponse())).toBe('source');
    expect(getMeetingFocusRole(sourceSummary, attachResponse({
      target_ref: sourceRef,
    }))).toBe('target');
    expect(getMeetingFocusRole(sourceSummary, attachResponse({
      attachments: [{ role: 'evidence', ref: sourceRef, projection_level: 'summary' }],
    }))).toBe('evidence');

    expect(getMeetingMissingContext([], attachResponse())).toBe('target');
    expect(getMeetingMissingContext([], attachResponse({ target_ref: targetRef }))).toBeNull();
    expect(getMeetingMissingContext([
      {
        ...baseNode,
        metadata: {
          target_ref: targetRef,
        },
      },
    ], attachResponse())).toBeNull();
  });
});
