import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import { attachResponse, summary } from './meetingWorkbenchTestData';

type BottomShellProps = React.ComponentProps<typeof AOLMeetingBottomShell>;

export function stubCompactViewport() {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches:
      query === '(max-width: 767px)'
        ? true
        : query === '(min-width: 768px) and (max-width: 1023px)'
          ? false
          : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
}

export function switchToContextWorkbenchPreset() {
  fireEvent.change(screen.getByTestId('meeting-workbench-preset-select'), {
    target: { value: 'context_workbench' },
  });
}

export function renderBottomShell(overrides: Partial<BottomShellProps> = {}) {
  const props: BottomShellProps = {
    workspaceId: 'ws-global',
    apiUrl: 'http://api.test',
    meetingId: 'mtg_global',
    summary,
    selection: null,
    attachResponse,
    surfaceRoute: '/workspaces/ws-global/capabilities/ig',
    onSwitchObject: vi.fn(),
    ...overrides,
  };

  return render(<AOLMeetingBottomShell {...props} />);
}
