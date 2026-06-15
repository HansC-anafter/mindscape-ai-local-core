import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import { attachResponse, summary } from './meetingWorkbenchTestData';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';
import { MeetingWorkSubgraphCanvas } from './MeetingWorkSubgraphCanvas';
import type { MeetingGraphEdge, MeetingNode, MeetingTranslate } from './meetingWorkbenchTypes';

function stubCompactViewport() {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches:
      query === '(max-width: 767px)'
        ? true
        : query === '(min-width: 768px) and (max-width: 1023px)'
          ? false
          : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
}

describe('AOLMeetingBottomShell layout and runtime graph', () => {
  installAOLMeetingBottomShellTestHarness();

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens as a graph-first bottom shell with collapsed inspector and console', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(screen.getByTestId('aol-meeting-bottom-shell')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-header-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-context-bar')).toHaveTextContent('Global Reference');
    expect(screen.getByTestId('meeting-work-role-chip')).toHaveTextContent(/Role: Source|\u89d2\u8272\uff1a\u4f86\u6e90/);
    expect(screen.getByTestId('meeting-work-status-chip')).toHaveTextContent('Outcome ready');
    expect(screen.getByTestId('meeting-work-next-chip')).toHaveTextContent('Ready for instruction');
    await waitFor(() => expect(screen.queryByTestId('meeting-work-missing-context-chip')).toBeNull());
    expect(screen.getByTestId('meeting-graph-view-work')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText(/nodes - .* trace events/)).toBeNull();
    const stage = screen.getByTestId('meeting-workbench-stage');
    const mainEditors = screen.getByTestId('meeting-workbench-main-editors');
    expect(stage).toBeInTheDocument();
    expect(mainEditors).toBeInTheDocument();
    const outliner = screen.getByTestId('meeting-object-outliner');
    const targetSection = within(outliner).getByTestId('meeting-object-outliner-section-target');
    const sourceSection = within(outliner).getByTestId('meeting-object-outliner-section-sources');
    const evidenceSection = within(outliner).getByTestId('meeting-object-outliner-section-evidence');
    const constraintsSection = within(outliner).getByTestId('meeting-object-outliner-section-constraints');
    const outputsSection = within(outliner).getByTestId('meeting-object-outliner-section-outputs');
    const reviewSection = within(outliner).getByTestId('meeting-object-outliner-section-review');
    expect(within(outliner).getByTestId('meeting-object-outliner-node-object')).toHaveTextContent('Global Reference');
    expect(sourceSection).toHaveTextContent('Global Reference');
    expect(await within(targetSection).findByText('storyboard pd_session_1')).toBeInTheDocument();
    expect(await within(reviewSection).findByText('storyboard_proposal proposal_01')).toBeInTheDocument();
    expect(await within(outputsSection).findByText('generated_asset asset_global')).toBeInTheDocument();
    fireEvent.click(within(outliner).getByTestId('meeting-object-outliner-node-object'));
    expect(within(outliner).getByTestId('meeting-object-outliner-node-object')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    fireEvent.click(screen.getByTestId('meeting-work-next-chip'));
    expect(screen.getByTestId('meeting-work-subgraph-focus')).toHaveTextContent('Ready for instruction');
    expect(screen.queryByTestId('meeting-object-context-panel')).toBeNull();
    expect(screen.queryByTestId('meeting-session-strip')).toBeNull();
    const canvas = screen.getByTestId('meeting-task-canvas');
    const ledgerStrip = screen.getByTestId('meeting-command-ledger-strip');
    const inspectorRail = screen.getByTestId('meeting-inspector-rail');
    expect(canvas).toBeInTheDocument();
    expect(screen.getByTestId('meeting-work-subgraph')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-lanes')).toBeNull();
    expect(mainEditors).toContainElement(inspectorRail);
    expect(screen.getByTestId('meeting-inspector-tab-object')).toHaveAttribute('title');
    expect(screen.getByTestId('meeting-inspector-tab-graph')).toHaveAttribute('title');
    expect(screen.getByTestId('meeting-inspector-tab-prompts')).toHaveAttribute('title');
    expect(stage).toContainElement(ledgerStrip);
    expect(mainEditors).not.toContainElement(ledgerStrip);
    expect(canvas).not.toContainElement(ledgerStrip);
    expect(screen.getByTestId('meeting-pack-tool-select')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    expect(await screen.findByTestId('meeting-session-strip')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-session-card-mtg_global')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-session-result-count')).toHaveTextContent('2/2');

    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    expect(screen.queryByTestId('meeting-sessions-popover')).toBeNull();
    expect(screen.getByTestId('meeting-object-context-panel')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    expect(screen.getAllByText('Ready for instruction').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('meeting-inspector-panel')).toBeNull();
    expect(screen.queryByTestId('meeting-console-drawer')).toBeNull();
  });

  it('uses a single secondary drawer on compact viewports', async () => {
    stubCompactViewport();

    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(screen.queryByTestId('meeting-inspector-rail')).toBeNull();
    expect(screen.queryByTestId('meeting-object-outliner')).toBeNull();

    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    expect(screen.getByTestId('meeting-secondary-drawer')).toHaveAttribute('data-secondary-surface', 'object');
    expect(screen.getByTestId('meeting-object-context-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-object-outliner')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    expect(screen.getByTestId('meeting-secondary-drawer')).toHaveAttribute('data-secondary-surface', 'sessions');
    expect(await screen.findByTestId('meeting-sessions-popover')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-object-context-panel')).toBeNull();

    fireEvent.click(screen.getByTestId('meeting-inspector-toggle'));
    expect(screen.getByTestId('meeting-secondary-drawer')).toHaveAttribute('data-secondary-surface', 'inspector');
    expect(screen.getByTestId('meeting-inspector-rail')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-inspector-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-sessions-popover')).toBeNull();

    fireEvent.click(screen.getByTestId('meeting-console-toggle'));
    expect(screen.getByTestId('meeting-secondary-drawer')).toHaveAttribute('data-secondary-surface', 'console');
    expect(screen.getByTestId('meeting-console-drawer')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-inspector-panel')).toBeNull();
  });

  it('renders meeting-owned execution graph nodes from task closure proof', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/fixture_pack"
        onSwitchObject={vi.fn()}
      />,
    );

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
    expect(screen.getByTestId('meeting-graph-node-closure-oap-global')).toHaveTextContent(
      'Action closed',
    );
    expect(screen.getByTestId('meeting-graph-node-relation-rel-output-target')).toHaveTextContent(
      'produced',
    );
    expect(screen.getByTestId('meeting-graph-node-output-object-global')).toHaveTextContent(
      'generated_asset',
    );

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
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/fixture_pack"
        onSwitchObject={vi.fn()}
      />,
    );

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

  it('filters meeting sessions from the header popover', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    fireEvent.change(await screen.findByTestId('meeting-session-search'), {
      target: { value: 'Other Reference' },
    });

    expect(screen.getByTestId('meeting-session-result-count')).toHaveTextContent('1/2');
    expect(screen.getByTestId('meeting-session-card-mtg_other')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-session-card-mtg_global')).toBeNull();
  });

  it('projects persisted meeting events into semantic lanes and collapses noisy action items', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

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

  it('auto-selects the newest workspace meeting when opened without an object-bound meeting id', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId={null}
        summary={null}
        selection={null}
        attachResponse={null}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_global');
    });
    expect(screen.getByLabelText('Meeting instruction')).toBeEnabled();
  });

  it('opens one inspector panel at a time inside the bottom shell', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-runtime'));
    expect(screen.getByTestId('meeting-inspector-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-workbench-main-editors')).toContainElement(
      screen.getByTestId('meeting-inspector-panel'),
    );
    expect(within(screen.getByTestId('meeting-inspector-panel')).getByText('Runtime binding')).toBeInTheDocument();
    expect(await screen.findByText('No runtime agents reported.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-session'));
    expect(within(screen.getByTestId('meeting-inspector-panel')).getByText('ws-global')).toBeInTheDocument();
    expect(within(screen.getByTestId('meeting-inspector-panel')).queryByText('Runtime binding')).toBeNull();
  });

  it('supports canvas-level zoom controls for the node graph', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

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
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    const canvas = screen.getByTestId('meeting-task-canvas');
    const content = screen.getByTestId('meeting-graph-canvas-content');

    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 145, clientY: 125 });

    expect(content).toHaveStyle({ transform: 'translate(45px, 25px) scale(1)' });
  });


});
