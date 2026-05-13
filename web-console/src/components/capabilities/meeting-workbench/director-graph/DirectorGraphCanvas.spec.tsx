import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
    onConnect,
    children,
  }: {
    nodes: Array<{ id: string; data?: { nodeType?: { label?: string; input_ports?: unknown[]; output_ports?: unknown[] } } }>;
    edges: unknown[];
    onNodeClick?: (event: React.MouseEvent, node: { id: string }) => void;
    onConnect?: (connection: { source: string; target: string; sourceHandle: string; targetHandle: string }) => void;
    children?: React.ReactNode;
  }) => (
    <div data-testid="reactflow-mock">
      {nodes.map((node) => (
        <button
          key={node.id}
          type="button"
          data-testid={`reactflow-node-${node.id}`}
          onClick={(event) => onNodeClick?.(event, node)}
        >
          {node.data?.nodeType?.label || node.id}
        </button>
      ))}
      <button
        type="button"
        data-testid="reactflow-connect-first"
        onClick={() => {
          const source = nodes[0];
          const target = nodes[1];
          if (!source || !target) {
            return;
          }
          const sourcePort = source.data?.nodeType?.output_ports?.[0] as { id?: string } | undefined;
          const targetPort = target.data?.nodeType?.input_ports?.[0] as { id?: string } | undefined;
          onConnect?.({
            source: source.id,
            target: target.id,
            sourceHandle: sourcePort?.id || 'output',
            targetHandle: targetPort?.id || 'input',
          });
        }}
      >
        connect
      </button>
      <div data-testid="reactflow-edge-count">{edges.length}</div>
      {children}
    </div>
  ),
  Handle: () => null,
  Background: () => <div data-testid="reactflow-background" />,
  Controls: () => <div data-testid="reactflow-controls" />,
  MiniMap: () => <div data-testid="director-graph-minimap" />,
  Position: { Left: 'left', Right: 'right' },
}));

import { DirectorGraphCanvas } from './DirectorGraphCanvas';
import { installAOLMeetingBottomShellTestHarness } from '../meetingWorkbenchTestHarness';
import type { MessageKey } from '@/lib/i18n';
import type { MeetingMentionItem } from '../meetingWorkbenchTypes';

const t = (key: MessageKey) => key;
const sceneMentionItems: MeetingMentionItem[] = [
  {
    id: 'scene-sc07',
    kind: 'scene',
    label: 'Scene 07',
    token: '@scene:sc07',
    description: 'Scene mention',
    ref: {
      id: 'sc07',
      kind: 'scene',
      token: '@scene:sc07',
      label: 'Scene 07',
      description: 'Scene mention',
      uri: 'mindscape://performance_direction/storyboard_scene/sc07',
      ownerPack: 'performance_direction',
      objectKind: 'storyboard_scene',
    },
  },
];

describe('DirectorGraphCanvas', () => {
  installAOLMeetingBottomShellTestHarness();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders contract node types, saves draft payloads, and compiles a command envelope', async () => {
    const onCommandEnvelope = vi.fn().mockResolvedValue(undefined);
    render(
      <DirectorGraphCanvas
        apiUrl="http://api.test"
        workspaceId="ws-global"
        meetingId="mtg_global"
        threadId="mtg_global"
        command="Compile graph @scene:sc07"
        selectedPackTool={null}
        mentionItems={sceneMentionItems}
        selectedObjectRef={null}
        onCommandEnvelope={onCommandEnvelope}
        t={t}
      />,
    );

    expect(await screen.findByTestId('director-graph-node-type-object_reference')).toBeInTheDocument();
    expect(await screen.findByTestId('director-graph-node-type-director_focus')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('director-graph-node-type-director_focus'));
    fireEvent.click(screen.getByTestId('director-graph-node-type-decision_point'));
    expect(screen.getAllByText('Director Focus').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Decision Point').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId('reactflow-connect-first'));
    fireEvent.click(screen.getByTestId('director-graph-save'));
    await waitFor(() => {
      expect(
        vi.mocked(global.fetch).mock.calls.some(([url, init]) =>
          String(url).includes('/composition-graph/drafts') &&
          String(init?.body || '').includes('director_focus') &&
          String(init?.body || '').includes('contract_edge'),
        ),
      ).toBe(true);
    });

    fireEvent.click(screen.getByTestId('director-graph-compile'));
    await waitFor(() => expect(onCommandEnvelope).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(
        vi.mocked(global.fetch).mock.calls.some(([url, init]) =>
          String(url).includes('/composition-graph/compile') &&
          String(init?.body || '').includes('@scene:sc07') &&
          String(init?.body || '').includes('storyboard_scene'),
        ),
      ).toBe(true);
    });
  });

  it('exports and imports portable graph JSON through the validation endpoint', async () => {
    render(
      <DirectorGraphCanvas
        apiUrl="http://api.test"
        workspaceId="ws-global"
        meetingId="mtg_global"
        threadId="mtg_global"
        command=""
        selectedPackTool={null}
        onCommandEnvelope={vi.fn().mockResolvedValue(undefined)}
        t={t}
      />,
    );

    fireEvent.click(await screen.findByTestId('director-graph-node-type-director_focus'));
    fireEvent.click(screen.getByTestId('director-graph-export'));
    expect(String((screen.getByTestId('director-graph-json') as HTMLTextAreaElement).value)).toContain('director_focus');

    fireEvent.click(screen.getByTestId('director-graph-import'));
    await waitFor(() => {
      expect(
        vi.mocked(global.fetch).mock.calls.some(([url]) =>
          String(url).includes('/composition-graph/import'),
        ),
      ).toBe(true);
    });
  });
});
