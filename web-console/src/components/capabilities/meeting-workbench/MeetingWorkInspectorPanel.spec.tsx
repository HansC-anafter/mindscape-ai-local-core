import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ObjectGraphProjection } from '@/lib/addressable-object-layer';
import { MeetingWorkInspectorContent } from './MeetingWorkInspectorPanel';
import { summary } from './meetingWorkbenchTestData';
import type { MeetingNode, MeetingTranslate, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';

const t: MeetingTranslate = (key) => {
  const labels: Partial<Record<Parameters<MeetingTranslate>[0], string>> = {
    meetingWorkbenchSelectedGuidance: 'Selected guidance',
    meetingWorkbenchGuidanceReason: 'Reason',
    meetingWorkbenchContextRelations: 'Context relations',
    meetingWorkbenchGuidanceCards: 'Guidance cards',
    meetingWorkbenchCommandTemplate: 'Command template',
    meetingWorkbenchTargetRef: 'Target',
    meetingWorkbenchProposalRef: 'Proposal',
    meetingWorkbenchRequiredContext: 'Required context',
    meetingWorkbenchReviewRoute: 'Review route',
    meetingWorkbenchLoadingRelations: 'Loading relations...',
    meetingWorkbenchNoBoundedRelations: 'No bounded relations',
    meetingWorkbenchNoGuidanceCards: 'No guidance cards projected',
  };
  return labels[key] || key;
};

const runtimeSnapshot: RuntimeInspectorSnapshot = {
  resolvedRuntime: null,
  dispatchChain: [],
  boundRuntimeIds: [],
  agents: [],
  loading: false,
  error: null,
};

const selectedGuidanceNode: MeetingNode = {
  id: 'object-guidance-fixture-director-framing',
  eyebrow: 'Guidance',
  title: 'Director framing',
  detail: 'Review framing before generation.',
  status: 'ready',
  kind: 'group',
  lane: 'graph',
  metadata: {
    guidance_id: 'director-framing',
    object_uri: summary.ref.uri,
  },
};

const projections: ObjectGraphProjection[] = [
  {
    ref: summary.ref,
    node_kind: 'reference',
    summary,
    relations: [
      {
        relation_kind: 'relates_to',
        direction: 'outbound',
        target_ref: {
          uri: 'mindscape://fixture_pack/storyboard/storyboard_01',
          owner_pack: 'fixture_pack',
          object_kind: 'storyboard',
          object_id: 'storyboard_01',
        },
      },
    ],
    guidance: [
      {
        id: 'director-framing',
        title: 'Director framing',
        description: 'Review framing before generation.',
        intent: 'plan',
        command_template: 'Draft a shot plan for @object:ref_global before generating assets.',
        review_label: 'Review shot proposal',
        review_routes: ['/review/proposal_01'],
        target_ref: {
          uri: 'mindscape://fixture_pack/generic_object/object_open',
          owner_pack: 'fixture_pack',
          object_kind: 'generic_object',
          object_id: 'object_open',
        },
        proposal_ref: {
          uri: 'mindscape://fixture_pack/storyboard_proposal/proposal_01',
          owner_pack: 'fixture_pack',
          object_kind: 'storyboard_proposal',
          object_id: 'proposal_01',
        },
        required_roles: ['target'],
      },
    ],
  },
];

describe('MeetingWorkInspectorContent', () => {
  it('shows selected guidance focus with command context and review routes', () => {
    render(
      <MeetingWorkInspectorContent
        activeInspector="graph"
        selectedNode={selectedGuidanceNode}
        runtimeSnapshot={runtimeSnapshot}
        workspaceId="ws-global"
        meetingId="mtg_global"
        summary={summary}
        attachResponse={null}
        objectGraphProjections={projections}
        objectGraphLoading={false}
        objectGraphError={null}
        commandImpact={null}
        t={t}
      />,
    );

    const selectedGuidance = screen.getByTestId('meeting-work-selected-guidance-card');
    expect(selectedGuidance).toHaveTextContent('Selected guidance');
    expect(selectedGuidance).toHaveTextContent('Director framing');
    expect(selectedGuidance).toHaveTextContent('Reason: Review framing before generation.');
    expect(selectedGuidance).toHaveTextContent('Command template:Draft a shot plan');
    expect(selectedGuidance).toHaveTextContent('Target: fixture_pack / generic_object / object_open');
    expect(selectedGuidance).toHaveTextContent('Proposal: fixture_pack / storyboard_proposal / proposal_01');
    expect(selectedGuidance).toHaveTextContent('Required context: target');
    expect(selectedGuidance).toHaveTextContent('Review shot proposal:/review/proposal_01');

    const guidancePanel = screen.getByTestId('meeting-work-guidance-panel');
    expect(within(guidancePanel).getByText(/relates_to/)).toBeInTheDocument();
  });
});
