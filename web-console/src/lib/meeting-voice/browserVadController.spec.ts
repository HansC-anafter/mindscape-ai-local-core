import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const vadMocks = vi.hoisted(() => ({
  create: vi.fn(),
  start: vi.fn(async () => undefined),
  pause: vi.fn(async () => undefined),
  destroy: vi.fn(async () => undefined),
  encodeWav: vi.fn(() => new ArrayBuffer(8)),
  toBase64: vi.fn(() => 'encoded-wav'),
}));

vi.mock('@ricky0123/vad-web', () => ({
  MicVAD: { new: vadMocks.create },
}));

vi.mock('./browserPcmWav', () => ({
  encodeBrowserPcm16Wav: vadMocks.encodeWav,
  arrayBufferToBase64: vadMocks.toBase64,
}));

import { createBrowserVadController } from './browserVadController';

describe('createBrowserVadController', () => {
  beforeEach(() => {
    vadMocks.create.mockResolvedValue({
      start: vadMocks.start,
      pause: vadMocks.pause,
      destroy: vadMocks.destroy,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('uses the installed VAD module lazily with local assets and emits 16 kHz WAV windows', async () => {
    const onSpeechStart = vi.fn();
    const onSpeechEnd = vi.fn(async () => undefined);
    const controller = await createBrowserVadController({
      onSpeechStart,
      onSpeechEnd,
    });
    const options = vadMocks.create.mock.calls[0][0];

    expect(options).toMatchObject({
      model: 'legacy',
      startOnLoad: false,
      baseAssetPath: '/vad/',
      onnxWASMBasePath: '/vad/',
    });
    options.onSpeechStart();
    const audio = new Float32Array([0.1, -0.1]);
    await options.onSpeechEnd(audio);
    expect(onSpeechStart).toHaveBeenCalledTimes(1);
    expect(vadMocks.encodeWav).toHaveBeenCalledWith(audio);
    expect(vadMocks.toBase64).toHaveBeenCalledWith(expect.any(ArrayBuffer));
    expect(onSpeechEnd).toHaveBeenCalledWith({
      audioBase64: 'encoded-wav',
      mimeType: 'audio/wav',
    });

    await controller.start();
    await controller.pause();
    await controller.destroy();
    expect(vadMocks.start).toHaveBeenCalledTimes(1);
    expect(vadMocks.pause).toHaveBeenCalledTimes(1);
    expect(vadMocks.destroy).toHaveBeenCalledTimes(1);
  });

  it('forwards WAV encoding errors without creating a fallback transport', async () => {
    const onError = vi.fn();
    vadMocks.encodeWav.mockImplementationOnce(() => {
      throw new Error('encode_failed');
    });
    await createBrowserVadController({
      onSpeechEnd: vi.fn(),
      onError,
    });
    const options = vadMocks.create.mock.calls[0][0];

    await options.onSpeechEnd(new Float32Array([0.2]));

    expect(onError).toHaveBeenCalledWith(new Error('encode_failed'));
  });
});
