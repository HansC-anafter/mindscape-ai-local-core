import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MeetingWorkSubgraphCanvas } from './MeetingWorkSubgraphCanvas';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';
import type { MeetingGraphEdge, MeetingNode, MeetingTranslate } from './meetingWorkbenchTypes';
import { renderBottomShell, switchToContextWorkbenchPreset } from './AOLMeetingBottomShellLayout.testHelpers';

describe('AOLMeetingBottomShell runtime graph layout', () => {
  installAOLMeetingBottomShellTestHarness();

  it('renders meeting-owned execution graph nodes from task closure proof', async () => {
    renderBottomShell({
      surfaceRoute: '/workspaces/ws-global/capabilities/fixture_pack',
    });

    switchToContextWorkbenchPreset();

    expect(await screen.findByTestId('meeting-graph-node-command-oap-global')).toHaveTextContent(
      'Produce generic asset',
    );
    const ledgerStrip = screen.getByTestId('meeting-command-ledger-strip');
    expect(within(ledgerStrip).getByTestId('meeting-command-ledger-entry-command-oap-global')).toHaveTextContent(
      'Produce generic asset',
    );
    expect(screen.getByTestId('meeting-work-provenance')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-provenance-edge-edge-closure-output')).toHaveTextContent('produced');
    expect(screen.getByTestId('meeting-work-step-command')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-node-command-event_user')).toHaveTextContent('#1 initial');
    expect(screen.getByTestId('meeting-graph-node-command-oap-global')).toHaveTextContent('#2 inserted');
    expect(screen.getByTestId('meeting-graph-node-run-task-global')).toHaveTextContent('fixture_runtime');
    expect(screen.getByTestId('meeting-graph-node-closure-oap-global')).toHaveTextContent('Action closed');
    expect(screen.getByTestId('meeting-graph-node-relation-rel-output-target')).toHaveTextContent('produced');
    expect(screen.getByTestId('meeting-graph-node-output-object-global')).toHaveTextContent('generated_asset');

    fireEvent.click(within(ledgerStrip).getByTestId('meeting-command-ledger-entry-command-oap-global'));

    const impactPanel = screen.getByTestId('meeting-command-impact-panel');
    expect(impactPanel).toHaveTextContent('Command impact');
    expect(impactPanel).toHaveTextContent('inserted');
    expect(impactPanel).toHaveTextContent('Edges');
    expect(within(impactPanel).getByText('3')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-node-run-task-global')).toHaveAttribute('data-impact-state', 'related');
    expect(screen.getByTestId('meeting-graph-node-output-object-global')).toHaveAttribute('data-impact-state', 'related');
  });

  it('groups overflow provenance edges without dropping runtime proof', () => {
    const nodes: MeetingNode[] = Array.from({ length: 9 }, (_, index) => ({
      id: `node-${index}`,
      eyebrow: index === 0 ? 'Meeting' : 'Run',
      title: `Node ${index}`,
      detail: `Node detail ${index}`,
      status: 'ready',
      kind: index === 0 ? 'meeting' : 'run',
      lane: index === 0 ? 'context' : 'runs',
    }));
    const edges: MeetingGraphEdge[] = Array.from({ length: 8 }, (_, index) => ({
      id: `edge-${index}`,
      from_id: `node-${index}`,
      to_id: `node-${index + 1}`,
      type: 'produced',
      label: `proof ${index}`,
    }));
    const t: MeetingTranslate = (key, params) => {
      if (key === 'meetingWorkbenchMoreProofEdges') {
        return `${params?.count} more proof edges`;
      }
      return key;
    };

    render(
      <MeetingWorkSubgraphCanvas
        nodes={nodes}
        edges={edges}
        selectedNodeId="node-0"
        commandImpact={null}
        onSelectNode={vi.fn()}
        t={t}
      />,
    );

    expect(screen.getByTestId('meeting-work-provenance')).toHaveTextContent('6/8');
    expect(screen.getByTestId('meeting-work-provenance-edge-edge-5')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-work-provenance-edge-edge-6')).toBeNull();
    expect(screen.getByTestId('meeting-work-provenance-overflow')).toHaveTextContent('2 more proof edges');
    expect(screen.getByTestId('meeting-work-provenance-overflow-edge-edge-6')).toHaveTextContent('Node 6');
    expect(screen.getByTestId('meeting-work-provenance-overflow-edge-edge-7')).toHaveTextContent('Node 8');
  });

  it('renders bounded object graph projections in the generic graph lane and inspector', async () => {
    renderBottomShell({
      surfaceRoute: '/workspaces/ws-global/capabilities/fixture_pack',
    });

    switchToContextWorkbenchPreset();

    const guidanceStep = await screen.findByTestId('meeting-work-step-guidance');
    expect(guidanceStep).toBeInTheDocument();
    expect(await screen.findByText(/1 bounded relation/)).toBeInTheDocument();
    expect(within(guidanceStep).getAllByText('Director framing').length).toBeGreaterThan(0);

    fireEvent.click(within(guidanceStep).getAllByText('Director framing')[0]);

    expect(screen.getByLabelText('Meeting instruction')).toHaveValue(
      'Draft a shot plan for @object:ref_global before generating assets.',
    );
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('directs');
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('Draft a shot plan');
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('Review shot proposal');
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('performance_direction / storyboard_proposal / proposal_01');

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-patch'));
    expect(screen.getByTestId('meeting-work-review-panel')).toHaveTextContent('Review shot proposal');
    expect(screen.getByTestId('meeting-work-review-panel')).toHaveTextContent('/review/proposal_01');
  });

  it('projects persisted meeting events into semantic lanes and collapses noisy action items', async () => {
    renderBottomShell();

    switchToContextWorkbenchPreset();

    expect(await screen.findByTestId('meeting-work-subgraph')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-step-focus')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-step-command')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-step-runtime')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-step-outcome')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-step-next')).toBeInTheDocument();
    expect(await screen.findByTestId('meeting-graph-node-command-event_user')).toHaveTextContent(
      'Create a 90 second reels script',
    );
    expect(screen.queryByTestId('meeting-graph-node-run-event_stage')).toBeNull();
    expect(screen.getByTestId('meeting-graph-node-result-event_result')).toHaveTextContent('0-10: opening shot');
    expect(screen.getByTestId('meeting-graph-node-group-action-items')).toHaveTextContent('Action Items - 20');
    expect(screen.queryByTestId('meeting-graph-node-event_action_1')).toBeNull();
    expect(await screen.findByTestId('meeting-graph-node-artifact-artifact_result')).toHaveTextContent(
      'Task Result: exec_result',
    );

    fireEvent.click(screen.getByTestId('meeting-graph-node-group-action-items'));
    expect(screen.getByTestId('meeting-inspector-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-trace-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-trace-filter-action_item')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('meeting-trace-event-list')).toHaveTextContent('Governance action item 1');
  });

  it('supports canvas-level zoom controls for the node graph', async () => {
    renderBottomShell();

    switchToContextWorkbenchPreset();

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-zoom-in'));
    expect(screen.getByText('110%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-zoom-out'));
    expect(screen.getByText('100%')).toBeInTheDocument();
    const canvas = screen.getByTestId('meeting-task-canvas');
    fireEvent.wheel(canvas, { deltaY: -12, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: -120, deltaX: 24, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(await screen.findByTestId('meeting-graph-node-command-oap-global'), {
      deltaY: -120,
      deltaX: 0,
      deltaMode: 0,
      clientX: 200,
      clientY: 100,
    });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: -120, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('110%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: 120, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-fit'));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('pans the graph canvas by dragging the background', async () => {
    renderBottomShell();

    switchToContextWorkbenchPreset();

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    const canvas = screen.getByTestId('meeting-task-canvas');
    const content = screen.getByTestId('meeting-graph-canvas-content');

    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 145, clientY: 125 });

    expect(content).toHaveStyle({ transform: 'translate(45px, 25px) scale(1)' });
  });
});
