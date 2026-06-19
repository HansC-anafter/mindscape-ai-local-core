import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HostRuntimeEventTimeline } from './HostRuntimeEventTimeline';
import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

function runtimeEvent(seq: number, eventType: string, payload: Record<string, unknown>): HostRuntimeEvent {
  return {
    workspace_id: 'ws_test',
    session_id: 'session_1',
    seq,
    event_type: eventType,
    payload,
    created_at: `2026-06-19T00:00:${String(seq).padStart(2, '0')}Z`,
  };
}

describe('HostRuntimeEventTimeline', () => {
  beforeEach(() => {
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = vi.fn();
    } else {
      vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => undefined);
    }
  });

  it('renders human stream labels and groups raw tool output delta chunks', () => {
    render(
      <HostRuntimeEventTimeline
        events={[
          runtimeEvent(1, 'session.created', { status: 'created' }),
          runtimeEvent(2, 'session.ready', { status: 'ready' }),
          runtimeEvent(3, 'item.started', { tool_name: 'codex_cli' }),
          runtimeEvent(4, 'tool.output.delta', { delta: 'Reading IG seed context. ' }),
          runtimeEvent(5, 'tool.output.delta', { delta: 'Summarizing cross-post signals.' }),
        ]}
      />,
    );

    expect(screen.getByTestId('host-runtime-current-activity')).toHaveTextContent('Current: Tool output');
    expect(screen.getByTestId('host-runtime-event-timeline')).toHaveTextContent('Session created');
    expect(screen.getByTestId('host-runtime-event-timeline')).toHaveTextContent('Tool started');
    expect(screen.getByTestId('host-runtime-event-timeline')).toHaveTextContent(
      'Reading IG seed context. Summarizing cross-post signals.',
    );
    expect(screen.getByTestId('host-runtime-event-timeline')).not.toHaveTextContent('tool.output.delta');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('uses readable host runtime progress payload before raw event names', () => {
    render(
      <HostRuntimeEventTimeline
        events={[
          runtimeEvent(1, 'runtime.progress', {
            phase: 'waiting_for_output',
            title: 'Codex CLI is working',
            detail: 'Waiting for Codex CLI output. The turn is still running.',
            status: 'running',
            raw_event_type: 'runtime.progress',
          }),
        ]}
      />,
    );

    expect(screen.getByTestId('host-runtime-current-activity')).toHaveTextContent('Current: Codex CLI is working');
    expect(screen.getByTestId('host-runtime-event-timeline')).toHaveTextContent(
      'Waiting for Codex CLI output. The turn is still running.',
    );
    expect(screen.getByTestId('host-runtime-event-timeline')).toHaveTextContent('running');
    expect(screen.getByTestId('host-runtime-event-timeline')).not.toHaveTextContent('Current: Tool output');
  });
});
