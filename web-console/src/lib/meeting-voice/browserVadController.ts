import { MicVAD, utils } from '@ricky0123/vad-web';

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

export async function createBrowserVadController(
  input: CreateBrowserVadInput,
): Promise<BrowserVadController> {
  const micVad = await MicVAD.new({
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
        const wavBuffer = utils.encodeWAV(audio, 1, 16000, 1, 16);
        await input.onSpeechEnd({
          audioBase64: utils.arrayBufferToBase64(wavBuffer),
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
