import { render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useProductOutcomeReview } from './useProductOutcomeReview';

const fetchSummary = vi.fn();
const subscribe = vi.fn(
  (_workspaceId: string, _options: unknown) => vi.fn(),
);

vi.mock('./api', () => ({
  fetchProductIterationSummary: (
    apiUrl: string,
    workspaceId: string,
    iterationId: string,
    signal: AbortSignal,
  ) => fetchSummary(apiUrl, workspaceId, iterationId, signal),
}));

vi.mock('@/components/workspace/eventProjector', () => ({
  subscribeEventStream: (workspaceId: string, options: unknown) => (
    subscribe(workspaceId, options)
  ),
}));

function Probe({ active }: { active: boolean }) {
  const result = useProductOutcomeReview({
    active,
    apiUrl: 'http://api.test',
    workspaceId: 'workspace:test',
    iterationId: 'iteration:test',
  });
  return <div data-state={result.loading ? 'loading' : 'idle'} />;
}

describe('useProductOutcomeReview', () => {
  afterEach(() => {
    fetchSummary.mockReset();
    subscribe.mockClear();
  });

  it('performs no hidden read and exactly one initial active read', async () => {
    fetchSummary.mockResolvedValue({
      iteration_id: 'iteration:test',
    });
    const rendered = render(<Probe active={false} />);
    expect(fetchSummary).not.toHaveBeenCalled();
    expect(subscribe).not.toHaveBeenCalled();
    rendered.rerender(<Probe active />);
    await waitFor(() => expect(fetchSummary).toHaveBeenCalledTimes(1));
    expect(subscribe).toHaveBeenCalledTimes(1);
  });

  it('does not refresh from a stale event after unmount', async () => {
    fetchSummary.mockResolvedValue({
      iteration_id: 'iteration:test',
    });
    const rendered = render(<Probe active />);
    await waitFor(() => expect(fetchSummary).toHaveBeenCalledTimes(1));
    const options = subscribe.mock.calls[0][1] as {
      onEvent: (event: { payload: Record<string, unknown> }) => void;
    };
    rendered.unmount();
    options.onEvent({
      payload: { iteration_id: 'iteration:test' },
    });
    await Promise.resolve();
    expect(fetchSummary).toHaveBeenCalledTimes(1);
  });
});
