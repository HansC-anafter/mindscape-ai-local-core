import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DEFAULT_AGENT_FREEFORM_PANELS } from './agentFreeformLayoutModel';
import { AgentFreeformCanvas } from './AgentFreeformCanvas';

describe('AgentFreeformCanvas', () => {
  it('renders validated freeform panels inside the RUNS workspace', () => {
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
    expect(screen.getByTestId('agent-freeform-panel-composer')).toHaveAttribute('data-panel-type', 'composer');
    expect(screen.getByTestId('host-runtime-composer')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-resource-state')).toHaveTextContent('No session');
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
