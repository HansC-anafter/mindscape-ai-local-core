import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';
import { renderBottomShell, switchToContextWorkbenchPreset } from './AOLMeetingBottomShellLayout.testHelpers';

describe('AOLMeetingBottomShell session surfaces', () => {
  installAOLMeetingBottomShellTestHarness();

  it('filters meeting sessions from the header popover', async () => {
    renderBottomShell();

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    fireEvent.change(await screen.findByTestId('meeting-session-search'), {
      target: { value: 'Other Reference' },
    });

    expect(screen.getByTestId('meeting-session-result-count')).toHaveTextContent('1/2');
    expect(screen.getByTestId('meeting-session-card-mtg_other')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-session-card-mtg_global')).toBeNull();
  });

  it('retries the meeting session popover after a transient load failure', async () => {
    const fetchMock = vi.mocked(global.fetch);
    const defaultFetch = fetchMock.getMockImplementation();
    let sessionLoadCount = 0;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions?limit=')) {
        sessionLoadCount += 1;
        if (sessionLoadCount === 1) {
          return new Response(JSON.stringify({ detail: 'database recovery' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          });
        }
      }
      if (!defaultFetch) {
        throw new Error(`Unhandled fetch: ${url}`);
      }
      return defaultFetch(input, init);
    });

    renderBottomShell();

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    expect(await screen.findByTestId('meeting-session-retry')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-session-strip')).toHaveTextContent('Failed to fetch meeting sessions: 500');

    fireEvent.click(screen.getByTestId('meeting-session-retry'));

    expect(await screen.findByTestId('meeting-session-card-mtg_global')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-session-retry')).toBeNull();
    expect(sessionLoadCount).toBe(2);
  });

  it('auto-selects the newest workspace meeting when opened without an object-bound meeting id', async () => {
    renderBottomShell({
      meetingId: null,
      summary: null,
      attachResponse: null,
    });

    switchToContextWorkbenchPreset();

    await waitFor(() => {
      expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_global');
    });
    expect(screen.getByLabelText('Meeting instruction')).toBeEnabled();
  });

  it('opens one inspector panel at a time inside the bottom shell', async () => {
    renderBottomShell();

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
});
