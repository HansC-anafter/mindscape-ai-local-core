import { afterEach, beforeEach, vi } from 'vitest';

import { createMeetingWorkbenchTestHarnessFetch } from './meetingWorkbenchTestHarnessFetch';

export function installAOLMeetingBottomShellTestHarness() {
  const originalFetch = global.fetch;

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    global.fetch = vi.fn(createMeetingWorkbenchTestHarnessFetch()) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

}
