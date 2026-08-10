import {
  arrayBufferToBase64,
  encodeBrowserPcm16Wav,
  MEETING_VOICE_SAMPLE_RATE,
} from '@/lib/meeting-voice/browserPcmWav';

const WORKSPACE_PCM_WORKLET_URL = '/voice/workspacePcmCapture.worklet.js';
const WORKSPACE_PCM_PROCESSOR_NAME = 'workspace-pcm-capture';

type BrowserAudioContextConstructor = new () => AudioContext;

function audioContextConstructor(): BrowserAudioContextConstructor | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const browserWindow = window as typeof window & {
    webkitAudioContext?: BrowserAudioContextConstructor;
  };
  return window.AudioContext || browserWindow.webkitAudioContext || null;
}

export function isWorkspaceBoundedVoiceCaptureSupported(): boolean {
  return Boolean(
    audioContextConstructor()
    && typeof AudioWorkletNode !== 'undefined'
    && typeof OfflineAudioContext !== 'undefined',
  );
}

export async function encodeWorkspaceVoiceBlob(blob: Blob): Promise<string> {
  return arrayBufferToBase64(await blob.arrayBuffer());
}

export type WorkspaceBoundedVoiceRecording = {
  audioBlob: Blob;
  mimeType: 'audio/wav';
};

export type WorkspaceBoundedVoiceRecorderHandle = {
  readonly state: 'recording' | 'inactive';
  stop: () => void;
  cancel: () => void;
};

type StartWorkspaceBoundedVoiceRecorderInput = {
  stream: MediaStream;
  onComplete: (
    recording: WorkspaceBoundedVoiceRecording | null,
  ) => Promise<void> | void;
  onError: (error: Error) => void;
};

type WorkspacePcmMessage =
  | { type: 'samples'; samples: Float32Array }
  | { type: 'flushed' };

function joinSampleChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  chunks.forEach((chunk) => {
    samples.set(chunk, offset);
    offset += chunk.length;
  });
  return samples;
}

async function resampleToMeetingVoice(
  samples: Float32Array,
  sourceSampleRate: number,
): Promise<Float32Array> {
  if (samples.length === 0) {
    return samples;
  }
  if (sourceSampleRate === MEETING_VOICE_SAMPLE_RATE) {
    return samples;
  }
  const outputLength = Math.max(
    1,
    Math.ceil(samples.length * MEETING_VOICE_SAMPLE_RATE / sourceSampleRate),
  );
  const offline = new OfflineAudioContext(
    1,
    outputLength,
    MEETING_VOICE_SAMPLE_RATE,
  );
  const inputBuffer = offline.createBuffer(1, samples.length, sourceSampleRate);
  inputBuffer.copyToChannel(samples, 0);
  const source = offline.createBufferSource();
  source.buffer = inputBuffer;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return new Float32Array(rendered.getChannelData(0));
}

export async function startWorkspaceBoundedVoiceRecorder(
  input: StartWorkspaceBoundedVoiceRecorderInput,
): Promise<WorkspaceBoundedVoiceRecorderHandle> {
  const AudioContextClass = audioContextConstructor();
  if (
    !AudioContextClass
    || typeof AudioWorkletNode === 'undefined'
    || typeof OfflineAudioContext === 'undefined'
  ) {
    input.stream.getTracks().forEach((track) => track.stop());
    throw new Error('workspace_voice_audio_worklet_unavailable');
  }

  const context = new AudioContextClass();
  const chunks: Float32Array[] = [];
  let captureState: 'recording' | 'inactive' = 'recording';
  let cancelled = false;
  let settled = false;
  let resourcesReleased = false;
  let source: MediaStreamAudioSourceNode | null = null;
  let worklet: AudioWorkletNode | null = null;
  let silentSink: GainNode | null = null;

  const releaseResources = async () => {
    if (resourcesReleased) {
      return;
    }
    resourcesReleased = true;
    captureState = 'inactive';
    source?.disconnect();
    worklet?.disconnect();
    silentSink?.disconnect();
    input.stream.getTracks().forEach((track) => track.stop());
    if (context.state !== 'closed') {
      await context.close().catch(() => undefined);
    }
  };

  const fail = async (caught: unknown) => {
    if (cancelled || settled) {
      return;
    }
    settled = true;
    await releaseResources();
    input.onError(
      caught instanceof Error
        ? caught
        : new Error('bounded_voice_recording_failed'),
    );
  };

  const finalize = async () => {
    if (cancelled || settled) {
      return;
    }
    settled = true;
    const sourceSampleRate = context.sampleRate;
    await releaseResources();
    try {
      const samples = await resampleToMeetingVoice(
        joinSampleChunks(chunks),
        sourceSampleRate,
      );
      if (cancelled) {
        return;
      }
      if (samples.length === 0) {
        await input.onComplete(null);
        return;
      }
      const wav = encodeBrowserPcm16Wav(samples);
      await input.onComplete({
        audioBlob: new Blob([wav], { type: 'audio/wav' }),
        mimeType: 'audio/wav',
      });
    } catch (caught) {
      input.onError(
        caught instanceof Error
          ? caught
          : new Error('bounded_voice_recording_failed'),
      );
    }
  };

  try {
    await context.audioWorklet.addModule(WORKSPACE_PCM_WORKLET_URL);
    source = context.createMediaStreamSource(input.stream);
    worklet = new AudioWorkletNode(context, WORKSPACE_PCM_PROCESSOR_NAME);
    silentSink = context.createGain();
    silentSink.gain.value = 0;
    worklet.port.onmessage = (event: MessageEvent<WorkspacePcmMessage>) => {
      if (cancelled || settled) {
        return;
      }
      if (event.data.type === 'samples') {
        chunks.push(new Float32Array(event.data.samples));
      } else if (event.data.type === 'flushed') {
        void finalize();
      }
    };
    worklet.onprocessorerror = () => {
      void fail(new Error('workspace_voice_audio_worklet_failed'));
    };
    source.connect(worklet);
    worklet.connect(silentSink);
    silentSink.connect(context.destination);
    if (context.state === 'suspended') {
      await context.resume();
    }
  } catch (caught) {
    await releaseResources();
    throw caught;
  }

  return {
    get state() {
      return captureState;
    },
    stop: () => {
      if (captureState !== 'recording' || cancelled || settled) {
        return;
      }
      captureState = 'inactive';
      worklet?.port.postMessage({ type: 'flush' });
    },
    cancel: () => {
      if (cancelled || settled) {
        return;
      }
      cancelled = true;
      void releaseResources();
    },
  };
}
