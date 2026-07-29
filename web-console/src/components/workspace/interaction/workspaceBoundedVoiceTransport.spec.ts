import { afterEach, describe, expect, it, vi } from 'vitest';

import { selectWorkspaceVoiceMimeType } from './workspaceBoundedVoiceTransport';

describe('workspaceBoundedVoiceTransport', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('selects the first supported browser MIME type, including MP4 fallback', () => {
    class FakeMediaRecorder {
      static isTypeSupported(value: string) {
        return value === 'audio/mp4';
      }
    }
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    expect(selectWorkspaceVoiceMimeType()).toBe('audio/mp4');
  });

  it('returns null without importing or starting a recorder', () => {
    vi.stubGlobal('MediaRecorder', undefined);
    expect(selectWorkspaceVoiceMimeType()).toBeNull();
  });
});
