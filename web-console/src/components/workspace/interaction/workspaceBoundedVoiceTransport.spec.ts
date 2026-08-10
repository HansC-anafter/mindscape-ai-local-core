import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  WORKSPACE_VOICE_CHUNK_TIMESLICE_MS,
  selectWorkspaceVoiceMimeType,
  startWorkspaceBoundedVoiceRecorder,
} from './workspaceBoundedVoiceTransport';

class FakeOfflineAudioContext {
  static decodeResult: 'valid' | 'invalid' = 'valid';

  async decodeAudioData(_buffer: ArrayBuffer): Promise<AudioBuffer> {
    if (FakeOfflineAudioContext.decodeResult === 'invalid') {
      throw new DOMException('invalid media');
    }
    return {
      duration: 1,
      length: 16000,
    } as AudioBuffer;
  }
}

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];

  static isTypeSupported(value: string) {
    return value === 'audio/webm;codecs=opus';
  }

  state: RecordingState = 'inactive';
  mimeType: string;
  timeslice: number | undefined;
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType || 'audio/webm';
    FakeMediaRecorder.instances.push(this);
  }

  start(timeslice?: number) {
    this.timeslice = timeslice;
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.onstop?.();
  }

  emit(data: Blob) {
    this.ondataavailable?.({ data } as BlobEvent);
  }

  fail(error: DOMException) {
    this.onerror?.(Object.assign(new Event('error'), { error }));
  }
}

describe('workspaceBoundedVoiceTransport', () => {
  afterEach(() => {
    FakeMediaRecorder.instances = [];
    FakeOfflineAudioContext.decodeResult = 'valid';
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

  it('records timesliced chunks, admits browser-decodable audio, and releases tracks once', async () => {
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext);
    const trackStop = vi.fn();
    const stream = {
      getTracks: () => [{ stop: trackStop }],
    } as unknown as MediaStream;
    let complete: ((value: unknown) => void) | undefined;
    const completed = new Promise((resolve) => {
      complete = resolve;
    });
    const onComplete = vi.fn((recording) => complete?.(recording));
    const onError = vi.fn();

    const handle = startWorkspaceBoundedVoiceRecorder({
      stream,
      mimeType: 'audio/webm;codecs=opus',
      onComplete,
      onError,
    });
    const recorder = FakeMediaRecorder.instances[0];
    recorder.emit(new Blob(['decodable-audio'], { type: recorder.mimeType }));
    handle.stop();
    const recording = await completed as { audioBlob: Blob; mimeType: string };

    expect(recorder.timeslice).toBe(WORKSPACE_VOICE_CHUNK_TIMESLICE_MS);
    expect(recording.audioBlob.size).toBeGreaterThan(0);
    expect(recording.mimeType).toBe('audio/webm;codecs=opus');
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('returns empty and never forwards an undecodable container as audio', async () => {
    FakeOfflineAudioContext.decodeResult = 'invalid';
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext);
    const onComplete = vi.fn();
    const handle = startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: vi.fn() }],
      } as unknown as MediaStream,
      mimeType: 'audio/webm;codecs=opus',
      onComplete,
      onError: vi.fn(),
    });
    const recorder = FakeMediaRecorder.instances[0];
    recorder.emit(new Blob(['container-only'], { type: recorder.mimeType }));
    handle.stop();

    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledWith(null));
  });

  it('cancels without completing and releases the microphone exactly once', async () => {
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext);
    const trackStop = vi.fn();
    const onComplete = vi.fn();
    const handle = startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: trackStop }],
      } as unknown as MediaStream,
      mimeType: 'audio/webm;codecs=opus',
      onComplete,
      onError: vi.fn(),
    });

    handle.cancel();
    await Promise.resolve();

    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('fails closed on recorder errors and releases the microphone', () => {
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext);
    const trackStop = vi.fn();
    const onComplete = vi.fn();
    const onError = vi.fn();
    startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: trackStop }],
      } as unknown as MediaStream,
      mimeType: 'audio/webm;codecs=opus',
      onComplete,
      onError,
    });

    const error = new DOMException('recorder failed', 'UnknownError');
    FakeMediaRecorder.instances[0].fail(error);

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({
      message: 'recorder failed',
      name: 'UnknownError',
    }));
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });
});
