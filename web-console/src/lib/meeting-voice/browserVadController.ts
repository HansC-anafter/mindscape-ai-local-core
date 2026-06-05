export type VadSpeechWindow = {
  audioBase64: string;
  mimeType: 'audio/wav';
};

export type BrowserVadController = {
  start: () => Promise<void>;
  pause: () => Promise<void>;
  destroy: () => Promise<void>;
};

export type CreateBrowserVadInput = {
  onSpeechStart?: () => void;
  onSpeechEnd: (window: VadSpeechWindow) => Promise<void> | void;
  onError?: (error: Error) => void;
};

type BrowserVadRuntime = {
  MicVAD: {
    new: (options: Record<string, unknown>) => Promise<BrowserVadController>;
  };
  utils: {
    encodeWAV: (
      audio: Float32Array,
      format: number,
      sampleRate: number,
      channels: number,
      bitsPerSample: number,
    ) => ArrayBuffer;
    arrayBufferToBase64: (buffer: ArrayBuffer) => string;
  };
};

function resolveBrowserVadRuntime(): BrowserVadRuntime {
  const runtime = (globalThis as { mindscapeVadRuntime?: BrowserVadRuntime }).mindscapeVadRuntime;
  if (!runtime?.MicVAD?.new || !runtime?.utils?.encodeWAV || !runtime?.utils?.arrayBufferToBase64) {
    throw new Error('browser_vad_runtime_unavailable');
  }
  return runtime;
}

export async function createBrowserVadController(
  input: CreateBrowserVadInput,
): Promise<BrowserVadController> {
  const vad = resolveBrowserVadRuntime();
  const micVad = await vad.MicVAD.new({
    model: 'legacy',
    startOnLoad: false,
    baseAssetPath: '/vad/',
    onnxWASMBasePath: '/vad/',
    onFrameProcessed: () => undefined,
    onVADMisfire: () => undefined,
    onSpeechRealStart: () => undefined,
    onSpeechStart: () => input.onSpeechStart?.(),
    onSpeechEnd: async (audio: Float32Array) => {
      try {
        const wavBuffer = vad.utils.encodeWAV(audio, 1, 16000, 1, 16);
        await input.onSpeechEnd({
          audioBase64: vad.utils.arrayBufferToBase64(wavBuffer),
          mimeType: 'audio/wav',
        });
      } catch (error) {
        input.onError?.(
          error instanceof Error ? error : new Error('vad_audio_window_failed'),
        );
      }
    },
  });
  return {
    start: () => micVad.start(),
    pause: () => micVad.pause(),
    destroy: () => micVad.destroy(),
  };
}
