import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';
import {
  renderBottomShell,
  stubCompactViewport,
  switchToContextWorkbenchPreset,
} from './AOLMeetingBottomShellLayout.testHelpers';

describe('AOLMeetingBottomShell layout modes', () => {
  installAOLMeetingBottomShellTestHarness();

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens as a runs-first bottom shell and keeps workbench presets behind a selector', async () => {
    renderBottomShell();

    expect(screen.getByTestId('aol-meeting-bottom-shell')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-header-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-view-runs')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByTestId('meeting-graph-view-work')).toBeNull();
    expect(screen.queryByTestId('meeting-graph-view-director')).toBeNull();
    expect(screen.getByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-composer-dock')).toBeVisible();
    expect(screen.getByTestId('agent-freeform-stream-panel')).toBeVisible();
    expect(screen.queryByTestId('agent-freeform-runtime-inspector')).toBeNull();

    switchToContextWorkbenchPreset();

    expect(screen.getByTestId('meeting-work-context-bar')).toHaveTextContent('Global Reference');
    expect(screen.getByTestId('meeting-work-role-chip')).toHaveTextContent(/Role: Source|\u89d2\u8272\uff1a\u4f86\u6e90/);
    expect(screen.getByTestId('meeting-work-status-chip')).toHaveTextContent('Outcome ready');
    expect(screen.getByTestId('meeting-work-next-chip')).toHaveTextContent('Ready for instruction');
    await waitFor(() => expect(screen.queryByTestId('meeting-work-missing-context-chip')).toBeNull());
    expect(screen.getByTestId('meeting-graph-view-runs')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText(/nodes - .* trace events/)).toBeNull();
    const stage = screen.getByTestId('meeting-workbench-stage');
    const mainEditors = screen.getByTestId('meeting-workbench-main-editors');
    expect(stage).toBeInTheDocument();
    expect(mainEditors).toBeInTheDocument();
    const outliner = screen.getByTestId('meeting-object-outliner');
    const targetSection = within(outliner).getByTestId('meeting-object-outliner-section-target');
    const sourceSection = within(outliner).getByTestId('meeting-object-outliner-section-sources');
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

    renderBottomShell();

    switchToContextWorkbenchPreset();

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

  it('defaults compact workbench routes into RUNS and keeps presets available', async () => {
    stubCompactViewport();

    renderBottomShell({
      surfaceRoute: '/workspaces/ws-global/capability-ui-hosts/ig?component=IGWorkbenchPage',
    });

    expect(screen.getByTestId('meeting-graph-view-mode-compact')).toBeInTheDocument();
    expect(await screen.findByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-runs-workspace-surface')).toHaveAttribute('data-layout-compact', 'true');
    expect(screen.getByTestId('meeting-graph-view-runs')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByTestId('meeting-task-canvas')).toBeNull();

    switchToContextWorkbenchPreset();
    expect(await screen.findByTestId('meeting-task-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-view-runs')).toHaveAttribute('aria-pressed', 'true');
  });
});
