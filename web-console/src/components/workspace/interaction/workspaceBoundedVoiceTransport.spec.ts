import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  encodeWorkspaceVoiceBlob,
  isWorkspaceBoundedVoiceCaptureSupported,
  startWorkspaceBoundedVoiceRecorder,
} from './workspaceBoundedVoiceTransport';

const audioMocks = vi.hoisted(() => ({
  addModule: vi.fn(async () => undefined),
  close: vi.fn(async () => undefined),
  resume: vi.fn(async () => undefined),
  sourceConnect: vi.fn(),
  sourceDisconnect: vi.fn(),
  workletConnect: vi.fn(),
  workletDisconnect: vi.fn(),
  sinkConnect: vi.fn(),
  sinkDisconnect: vi.fn(),
}));

class FakeAudioContext {
  audioWorklet = { addModule: audioMocks.addModule };
  destination = {} as AudioDestinationNode;
  sampleRate = 48000;
  state: AudioContextState = 'running';
  close = audioMocks.close;
  resume = audioMocks.resume;

  createMediaStreamSource() {
    return {
      connect: audioMocks.sourceConnect,
      disconnect: audioMocks.sourceDisconnect,
    } as unknown as MediaStreamAudioSourceNode;
  }

  createGain() {
    return {
      gain: { value: 1 },
      connect: audioMocks.sinkConnect,
      disconnect: audioMocks.sinkDisconnect,
    } as unknown as GainNode;
  }
}

class FakeAudioWorkletNode {
  static instances: FakeAudioWorkletNode[] = [];
  port = {
    onmessage: null as ((event: MessageEvent) => void) | null,
    postMessage: vi.fn(),
  };
  onprocessorerror: (() => void) | null = null;
  connect = audioMocks.workletConnect;
  disconnect = audioMocks.workletDisconnect;

  constructor(_context: AudioContext, readonly name: string) {
    FakeAudioWorkletNode.instances.push(this);
  }

  emit(data: unknown) {
    this.port.onmessage?.({ data } as MessageEvent);
  }
}

class FakeOfflineAudioContext {
  static constructorArgs: unknown[] = [];
  destination = {} as AudioDestinationNode;
  private samples = new Float32Array();

  constructor(...args: unknown[]) {
    FakeOfflineAudioContext.constructorArgs = args;
  }

  createBuffer() {
    return {
      copyToChannel: (samples: Float32Array) => {
        this.samples = new Float32Array(samples);
      },
    } as unknown as AudioBuffer;
  }

  createBufferSource() {
    return {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
    } as unknown as AudioBufferSourceNode;
  }

  async startRendering() {
    const rendered = this.samples.length > 0
      ? new Float32Array([0.25, -0.25])
      : new Float32Array();
    return {
      getChannelData: () => rendered,
    } as unknown as AudioBuffer;
  }
}

describe('workspaceBoundedVoiceTransport', () => {
  beforeEach(() => {
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
    vi.stubGlobal('OfflineAudioContext', FakeOfflineAudioContext);
  });

  afterEach(() => {
    FakeAudioWorkletNode.instances = [];
    FakeOfflineAudioContext.constructorArgs = [];
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('fails closed when the browser PCM capture seam is unavailable', () => {
    vi.stubGlobal('AudioWorkletNode', undefined);
    expect(isWorkspaceBoundedVoiceCaptureSupported()).toBe(false);
  });

  it('uses the shared browser base64 contract for bounded WAV blobs', async () => {
    await expect(encodeWorkspaceVoiceBlob(new Blob([new Uint8Array([0, 1, 2])]))).resolves
      .toBe('AAEC');
  });

  it('keeps the worklet leaf bounded to PCM chunking and explicit flush', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'public/voice/workspacePcmCapture.worklet.js'),
      'utf8',
    );
    expect(source).toContain('this.chunkSize = 4096');
    expect(source).toContain("event.data?.type !== 'flush'");
    expect(source).toContain("this.port.postMessage({ type: 'flushed' })");
    expect(source).not.toMatch(/fetch\(|WebSocket|setInterval|setTimeout|MediaRecorder/);
  });

  it('captures PCM, flushes once, resamples to 16 kHz WAV, and releases once', async () => {
    const trackStop = vi.fn();
    const onComplete = vi.fn();
    const onError = vi.fn();
    const handle = await startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: trackStop }],
      } as unknown as MediaStream,
      onComplete,
      onError,
    });
    const node = FakeAudioWorkletNode.instances[0];

    expect(audioMocks.addModule).toHaveBeenCalledWith(
      '/voice/workspacePcmCapture.worklet.js',
    );
    expect(node.name).toBe('workspace-pcm-capture');
    handle.stop();
    expect(node.port.postMessage).toHaveBeenCalledWith({ type: 'flush' });
    node.emit({ type: 'samples', samples: new Float32Array([0.1, -0.1]) });
    node.emit({ type: 'flushed' });

    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const recording = onComplete.mock.calls[0][0] as { audioBlob: Blob; mimeType: string };
    expect(recording.mimeType).toBe('audio/wav');
    expect(new Uint8Array(await recording.audioBlob.arrayBuffer()).slice(0, 4))
      .toEqual(new Uint8Array([82, 73, 70, 70]));
    expect(FakeOfflineAudioContext.constructorArgs).toEqual([1, 1, 16000]);
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(audioMocks.close).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('returns empty for a flushed capture with zero PCM frames', async () => {
    const onComplete = vi.fn();
    const handle = await startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: vi.fn() }],
      } as unknown as MediaStream,
      onComplete,
      onError: vi.fn(),
    });
    handle.stop();
    FakeAudioWorkletNode.instances[0].emit({ type: 'flushed' });

    await vi.waitFor(() => expect(onComplete).toHaveBeenCalledWith(null));
  });

  it('cancels without completion and releases the microphone exactly once', async () => {
    const trackStop = vi.fn();
    const onComplete = vi.fn();
    const handle = await startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: trackStop }],
      } as unknown as MediaStream,
      onComplete,
      onError: vi.fn(),
    });

    handle.cancel();
    handle.cancel();
    await vi.waitFor(() => expect(audioMocks.close).toHaveBeenCalledTimes(1));
    expect(trackStop).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('fails closed on worklet processor errors', async () => {
    const onError = vi.fn();
    await startWorkspaceBoundedVoiceRecorder({
      stream: {
        getTracks: () => [{ stop: vi.fn() }],
      } as unknown as MediaStream,
      onComplete: vi.fn(),
      onError,
    });

    FakeAudioWorkletNode.instances[0].onprocessorerror?.();
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith(
      new Error('workspace_voice_audio_worklet_failed'),
    ));
  });
});
