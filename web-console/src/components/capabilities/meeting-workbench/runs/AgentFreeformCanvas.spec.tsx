import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DEFAULT_AGENT_FREEFORM_PANELS } from './agentFreeformLayoutModel';
import { AgentFreeformCanvas } from './AgentFreeformCanvas';

describe('AgentFreeformCanvas', () => {
  it('keeps composer and stream visible as floating canvas panels', () => {
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
    expect(screen.getByTestId('agent-freeform-composer-dock')).toHaveStyle({ left: '20px', top: '64px' });
    expect(screen.getByTestId('agent-freeform-stream-panel')).toHaveAttribute('data-panel-type', 'timeline');
    expect(screen.getByTestId('agent-freeform-stream-panel')).toHaveStyle({ height: '360px' });
    expect(screen.getByTestId('host-runtime-prompt')).toBeVisible();
    expect(screen.queryByTestId('agent-freeform-panel-object_context')).toBeNull();
    expect(screen.queryByTestId('agent-freeform-panel-tool_calls')).toBeNull();
    expect(screen.queryByTestId('agent-freeform-runtime-tool-rail')).toBeNull();
    expect(screen.queryByTestId('agent-freeform-runtime-inspector')).toBeNull();
    expect(screen.getByTestId('agent-freeform-inspector-collapsed')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-composer')).toBeInTheDocument();
  });

  it('keeps runs inspector collapsed until the user opens it', () => {
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

    expect(screen.getByTestId('agent-freeform-inspector-collapsed')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-freeform-runtime-inspector')).toBeNull();

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-open'));

    expect(screen.getByTestId('agent-freeform-inspector-tabs')).toHaveTextContent('Runtime');
    expect(screen.getByTestId('agent-freeform-inspector-tabs')).toHaveTextContent('Graph context');
    expect(screen.queryByTestId('agent-freeform-dock-button-object_context')).toBeNull();

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-tab-object_context'));

    expect(screen.getByTestId('agent-freeform-side-panel-object_context')).toHaveAttribute('data-panel-type', 'object_context');
    expect(screen.getByTestId('host-runtime-object-context')).toHaveTextContent('Graph selection');

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-tab-resource_state'));

    expect(screen.getByTestId('agent-freeform-side-panel-resource_state')).toHaveAttribute('data-panel-type', 'resource_state');
    expect(screen.getByTestId('host-runtime-resource-state')).toHaveTextContent('No session');

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-close'));

    expect(screen.queryByTestId('agent-freeform-runtime-inspector')).toBeNull();
    expect(screen.getByTestId('agent-freeform-inspector-collapsed')).toBeInTheDocument();
  });

  it('supports canvas zoom and quick floating panel positioning', () => {
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

    expect(screen.getByTestId('agent-freeform-zoom-value')).toHaveTextContent('100%');
    fireEvent.click(screen.getByTestId('agent-freeform-zoom-in'));
    expect(screen.getByTestId('agent-freeform-zoom-value')).toHaveTextContent('110%');

    fireEvent.click(screen.getByTestId('agent-freeform-call-composer'));
    expect(screen.getByTestId('agent-freeform-composer-dock')).toBeVisible();
    fireEvent.click(screen.getByTestId('agent-freeform-call-stream'));
    expect(screen.getByTestId('agent-freeform-stream-panel')).toBeVisible();
    fireEvent.click(screen.getByTestId('agent-freeform-pin-composer'));
    expect(screen.getByTestId('agent-freeform-pin-composer')).toHaveAttribute('aria-pressed', 'false');

    fireEvent.keyDown(window, { key: 'g' });
    fireEvent.keyDown(window, { key: 'i' });
    expect(screen.getByTestId('agent-freeform-runtime-inspector')).toBeInTheDocument();
  });

  it('drags floating panels with the Move handle instead of jumping fixed presets', () => {
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

    const canvas = screen.getByTestId('agent-freeform-mind-map-canvas');
    const composer = screen.getByTestId('agent-freeform-composer-dock');
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 900,
      bottom: 700,
      width: 900,
      height: 700,
      toJSON: () => ({}),
    } as DOMRect);
    vi.spyOn(composer, 'getBoundingClientRect').mockReturnValue({
      x: 20,
      y: 64,
      left: 20,
      top: 64,
      right: 420,
      bottom: 248,
      width: 400,
      height: 184,
      toJSON: () => ({}),
    } as DOMRect);

    fireEvent.pointerDown(screen.getByTestId('agent-freeform-move-composer'), {
      clientX: 30,
      clientY: 74,
    });
    fireEvent.pointerMove(window, {
      clientX: 130,
      clientY: 174,
    });
    fireEvent.pointerUp(window);

    expect(composer).toHaveStyle({ left: '120px', top: '164px' });
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

    fireEvent.click(screen.getByTestId('agent-freeform-inspector-open'));
    fireEvent.click(screen.getByTestId('agent-freeform-inspector-tab-resource_state'));

    expect(screen.getByTestId('host-runtime-resource-state')).toHaveTextContent('bridge_unavailable');
  });

  it('offers a one-click bridge start action when the shared CLI bridge is not registered', () => {
    const onStartBridge = vi.fn();
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
        runtimeStatus={{ enabled: true, total_bridges: 0, runtime_surfaces: ['codex_cli'], bridges: [] }}
        bridgeService={{
          service: 'cli_bridge',
          workspace_id: 'ws_test',
          supported: true,
          installed: true,
          loaded: true,
          running: false,
          state: 'stopped',
          auto_recovery: true,
        }}
        meetingId="mtg_1"
        selectedObjectRef={null}
        isStarting={false}
        error={null}
        onSubmitPrompt={vi.fn()}
        onStartBridge={onStartBridge}
        onSelectPanel={vi.fn()}
        onResetLayout={vi.fn()}
        onToggleLocked={vi.fn()}
      />,
    );

    expect(screen.getByTestId('agent-freeform-canvas')).toHaveTextContent('bridge_unavailable');
    fireEvent.click(screen.getByTestId('host-runtime-start-bridge'));

    expect(onStartBridge).toHaveBeenCalledTimes(1);
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
