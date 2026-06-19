import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HostRuntimeSettlementCards } from './HostRuntimeSettlementCards';

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

describe('HostRuntimeSettlementCards', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders meeting_graph_content_settlement cards in RUNS trace cards without polling transcripts', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({
        artifacts: [{
          id: 'artifact_trace_1',
          title: 'RUNS TRACE settlement',
          content_preview: 'Preview run and trace settlement',
          metadata: { run_id: 'run_27' },
          execution_id: 'exec_trace_1',
        }],
      }))
      .mockResolvedValueOnce(jsonResponse({
        id: 'artifact_trace_1',
        title: 'RUNS TRACE settlement',
        content: { settlement_summary: 'Full run trace settlement detail' },
      }));

    render(<HostRuntimeSettlementCards apiUrl="http://api.test" workspaceId="ws_trace" />);

    expect(await screen.findByText('RUNS TRACE settlement')).toBeInTheDocument();
    expect(screen.getByText('Preview run and trace settlement')).toBeInTheDocument();
    expect(screen.getByText('run_27')).toBeInTheDocument();

    const listUrl = String(fetchMock.mock.calls[0][0]);
    expect(listUrl).toContain('/api/v1/workspaces/ws_trace/artifacts');
    expect(listUrl).toContain('playbook_code=meeting_graph_content_settlement');
    expect(listUrl).toContain('include_content=false');
    expect(listUrl).toContain('include_preview=true');

    fireEvent.click(screen.getByRole('button', { name: /detail/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/v1/artifacts/artifact_trace_1');
    expect(String(fetchMock.mock.calls[1][0])).toContain('include_content=true');
    expect(await screen.findByTestId('host-runtime-settlement-detail')).toHaveTextContent('Full run trace settlement detail');
  });
});
