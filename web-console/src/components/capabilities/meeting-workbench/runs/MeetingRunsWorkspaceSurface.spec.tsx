import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MeetingRunsWorkspaceSurface } from './MeetingRunsWorkspaceSurface';

const submitPrompt = vi.fn();

vi.mock('./useHostRuntimeRunSession', () => ({
  useHostRuntimeRunSession: () => ({
    status: { enabled: true, total_bridges: 1, runtime_surfaces: ['codex_cli'], bridges: [] },
    session: {
      id: 'session_1',
      execution_id: 'exec_1',
      workspace_id: 'ws_test',
      runtime_surface: 'codex_cli',
      runtime_id: 'codex_cli',
      status: 'ready',
      cwd: '/workspace',
      last_event_seq: 0,
    },
    events: [
      {
        workspace_id: 'ws_test',
        session_id: 'session_1',
        seq: 1,
        event_type: 'governance.snapshot.recorded',
        payload: {
          governance_trace_ref: 'host-runtime:ws_test:abc',
          intent_ref: { source: 'test' },
          policy_ref: { source: 'test' },
        },
        created_at: '2026-06-16T00:00:00Z',
      },
    ],
    bridgeService: null,
    isStarting: false,
    isStartingBridge: false,
    error: null,
    lastSeq: 1,
    startBridge: vi.fn(),
    submitPrompt,
  }),
}));

describe('MeetingRunsWorkspaceSurface', () => {
  it('mounts AgentFreeformCanvas as the only RUNS workspace surface', () => {
    render(
      <MeetingRunsWorkspaceSurface
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_1"
        selectedObjectRef={null}
      />,
    );

    expect(screen.getByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-mind-map-canvas')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-lanes')).not.toBeInTheDocument();
    expect(screen.queryByTestId('host-runtime-governance-context')).toBeNull();

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-open'));
    fireEvent.click(screen.getByTestId('agent-freeform-inspector-tab-trace_cards'));

    expect(screen.getByTestId('host-runtime-governance-context')).toHaveTextContent('host-runtime:ws_test:abc');
  });

  it('routes composer submit through host runtime run session hook', () => {
    render(
      <MeetingRunsWorkspaceSurface
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_1"
        selectedObjectRef={null}
      />,
    );

    fireEvent.change(screen.getByTestId('host-runtime-prompt'), {
      target: { value: 'Use the meeting engine' },
    });
    fireEvent.click(screen.getByTestId('host-runtime-submit'));

    expect(submitPrompt).toHaveBeenCalledWith('Use the meeting engine');
  });

  it('uses the surface as the compact mobile scroll owner', () => {
    render(
      <MeetingRunsWorkspaceSurface
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_1"
        selectedObjectRef={null}
        compactLayout
      />,
    );

    const surface = screen.getByTestId('meeting-runs-workspace-surface');
    const canvas = screen.getByTestId('agent-freeform-canvas');
    expect(surface).toHaveAttribute('data-layout-compact', 'true');
    expect(surface).toHaveClass('overflow-y-auto');
    expect(canvas).toHaveAttribute('data-layout-compact', 'true');
    expect(canvas).toHaveClass('overflow-visible');
    expect(screen.getByTestId('agent-freeform-mobile-stack')).toBeInTheDocument();
  });
});
