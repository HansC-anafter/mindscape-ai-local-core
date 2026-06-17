import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DEFAULT_AGENT_FREEFORM_PANELS } from './agentFreeformLayoutModel';
import { AgentFreeformCanvas } from './AgentFreeformCanvas';

describe('AgentFreeformCanvas', () => {
  it('keeps the RUNS center as a mind-map canvas with only the composer dock', () => {
    render(
      <AgentFreeformCanvas
        apiUrl="http://api.test"
        layout={{
          panels: DEFAULT_AGENT_FREEFORM_PANELS,
          locked: false,
          selectedPanelId: 'composer',
          decisions: [],
        }}
        events={[]}
        session={null}
        meetingId="mtg_1"
        selectedObjectRef={null}
        isStarting={false}
        error={null}
        onSubmitPrompt={vi.fn()}
        onSelectPanel={vi.fn()}
        onResetLayout={vi.fn()}
        onToggleLocked={vi.fn()}
      />,
    );

    expect(screen.getByTestId('agent-freeform-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-mind-map-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-composer-dock')).toHaveAttribute('data-panel-type', 'composer');
    expect(screen.queryByTestId('agent-freeform-panel-object_context')).toBeNull();
    expect(screen.queryByTestId('agent-freeform-panel-tool_calls')).toBeNull();
    expect(screen.getByTestId('agent-freeform-runtime-tool-rail')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-composer')).toBeInTheDocument();
  });

  it('moves runtime data panels into the right-side tool rail', () => {
    render(
      <AgentFreeformCanvas
        apiUrl="http://api.test"
        layout={{
          panels: DEFAULT_AGENT_FREEFORM_PANELS,
          locked: false,
          selectedPanelId: 'composer',
          decisions: [],
        }}
        events={[]}
        session={null}
        meetingId="mtg_1"
        selectedObjectRef={null}
        isStarting={false}
        error={null}
        onSubmitPrompt={vi.fn()}
        onSelectPanel={vi.fn()}
        onResetLayout={vi.fn()}
        onToggleLocked={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('agent-freeform-dock-button-object_context'));

    expect(screen.getByTestId('agent-freeform-side-panel-object_context')).toHaveAttribute('data-panel-type', 'object_context');
    expect(screen.getByTestId('host-runtime-object-context')).toHaveTextContent('Graph selection');
    expect(screen.queryByTestId('agent-freeform-side-panel-resource_state')).toBeNull();

    fireEvent.click(screen.getByTestId('agent-freeform-dock-button-resource_state'));

    expect(screen.getByTestId('agent-freeform-side-panel-resource_state')).toHaveAttribute('data-panel-type', 'resource_state');
    expect(screen.getByTestId('host-runtime-resource-state')).toHaveTextContent('No session');
  });

  it('promotes bridge failures over session ready state', () => {
    render(
      <AgentFreeformCanvas
        apiUrl="http://api.test"
        layout={{
          panels: DEFAULT_AGENT_FREEFORM_PANELS,
          locked: false,
          selectedPanelId: 'composer',
          decisions: [],
        }}
        events={[
          {
            workspace_id: 'ws_test',
            session_id: 'session_1',
            seq: 1,
            event_type: 'session.ready',
            payload: { status: 'ready' },
            created_at: '2026-06-18T00:00:00Z',
          },
          {
            workspace_id: 'ws_test',
            session_id: 'session_1',
            seq: 2,
            event_type: 'turn.failed',
            payload: { reason: 'bridge_unavailable' },
            created_at: '2026-06-18T00:00:01Z',
          },
        ]}
        session={{
          id: 'session_1',
          execution_id: 'exec_1',
          workspace_id: 'ws_test',
          runtime_surface: 'codex_cli',
          runtime_id: 'codex_cli',
          status: 'ready',
          cwd: '/workspace',
          last_event_seq: 2,
        }}
        runtimeStatus={{ enabled: true, total_bridges: 1, runtime_surfaces: ['codex_cli'], bridges: [{}] }}
        meetingId="mtg_1"
        selectedObjectRef={null}
        isStarting={false}
        error={null}
        onSubmitPrompt={vi.fn()}
        onSelectPanel={vi.fn()}
        onResetLayout={vi.fn()}
        onToggleLocked={vi.fn()}
      />,
    );

    expect(screen.getByTestId('agent-freeform-canvas')).toHaveTextContent('bridge_unavailable');

    fireEvent.click(screen.getByTestId('agent-freeform-dock-button-resource_state'));

    expect(screen.getByTestId('host-runtime-resource-state')).toHaveTextContent('bridge_unavailable');
  });

  it('submits prompts through the host runtime composer', () => {
    const onSubmitPrompt = vi.fn();
    render(
      <AgentFreeformCanvas
        apiUrl="http://api.test"
        layout={{
          panels: DEFAULT_AGENT_FREEFORM_PANELS,
          locked: false,
          selectedPanelId: 'composer',
          decisions: [],
        }}
        events={[]}
        session={null}
        meetingId="mtg_1"
        selectedObjectRef={null}
        isStarting={false}
        error={null}
        onSubmitPrompt={onSubmitPrompt}
        onSelectPanel={vi.fn()}
        onResetLayout={vi.fn()}
        onToggleLocked={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByTestId('host-runtime-prompt'), {
      target: { value: 'Inspect current meeting state' },
    });
    fireEvent.click(screen.getByTestId('host-runtime-submit'));

    expect(onSubmitPrompt).toHaveBeenCalledWith('Inspect current meeting state');
  });
});
