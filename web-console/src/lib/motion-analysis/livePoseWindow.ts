'use client';

import {
  buildCaptureMotionWindowMetadata,
  deriveMediaPipePoseCaptureSample,
  type CapturePoseSampleMetrics,
} from './captureMotionMetrics';

export type PoseSampleSummary = {
  timestampMs: number;
  confidence: number;
  visiblePointCount: number;
  totalPointCount: number;
  captureMetrics?: CapturePoseSampleMetrics | null;
};

export type MotionWindowSummary = {
  window_id: string;
  live_session_id: string;
  ts_start_ms: number;
  ts_end_ms: number;
  skeleton_family: 'mediapipe_pose_33';
  confidence_stats: Record<string, number>;
  scores: Record<string, number>;
  findings: string[];
  keypoint_frame_count: number;
  metadata: Record<string, unknown>;
};

export type LivePoseWindowAdapterStatus = {
  state: 'ready' | 'loading' | 'unavailable';
  reason?: string;
};

export type LivePoseWindowAdapter = {
  provider: string;
  getStatus?: () => LivePoseWindowAdapterStatus;
  estimate: (
    video: HTMLVideoElement,
    timestampMs: number,
  ) => Promise<PoseSampleSummary | null>;
  dispose?: () => void;
};

export type LivePoseWindowControllerStatus = {
  state:
    | 'idle'
    | 'active'
    | 'waiting_video'
    | 'provider_unavailable'
    | 'append_error'
    | 'stopped';
  reason?: string;
  appendedWindowCount: number;
  lastWindowId?: string;
};

export type LivePoseWindowController = {
  start: () => void;
  stop: () => void;
  getStatus: () => LivePoseWindowControllerStatus;
};

type LivePoseWindowScheduler = {
  requestFrame: (callback: FrameRequestCallback) => number;
  cancelFrame: (handle: number) => void;
};

type LivePoseWindowAccumulatorInput = {
  liveSessionId: string;
  windowMs?: number;
  maxSamples?: number;
  metadata?: Record<string, unknown>;
};

type LivePoseWindowControllerInput = LivePoseWindowAccumulatorInput & {
  video: HTMLVideoElement;
  adapter?: LivePoseWindowAdapter;
  appendMotionWindow: (
    summary: MotionWindowSummary,
    receivedAtMs: number,
  ) => Promise<void> | void;
  sampleFps?: number;
  scheduler?: LivePoseWindowScheduler;
  now?: () => number;
  onStatus?: (status: LivePoseWindowControllerStatus) => void;
};

type BrowserMediaPipeAdapterOptions = {
  wasmAssetPath?: string;
  modelAssetPath?: string;
};

type MediaPipePoseDetector = {
  detectForVideo: (video: HTMLVideoElement, timestampMs: number) => unknown;
  close?: () => void;
};

const DEFAULT_SAMPLE_FPS = 15;
const DEFAULT_WINDOW_MS = 2000;
const DEFAULT_MAX_SAMPLES = 30;
const MIN_VIDEO_READY_STATE = 2;

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

function average(values: number[]): number {
  if (!values.length) {
    return 0;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function roundMetric(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function createDefaultScheduler(): LivePoseWindowScheduler {
  return {
    requestFrame: (callback) => window.requestAnimationFrame(callback),
    cancelFrame: (handle) => window.cancelAnimationFrame(handle),
  };
}

function createDefaultNow(): () => number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return () => performance.now();
  }
  return () => Date.now();
}

export function createUnavailablePoseAdapter(reason: string): LivePoseWindowAdapter {
  return {
    provider: 'mediapipe_pose',
    getStatus: () => ({ state: 'unavailable', reason }),
    estimate: async () => null,
  };
}

function summarizePoints(points: unknown, timestampMs: number): PoseSampleSummary | null {
  if (!Array.isArray(points) || !points.length) {
    return null;
  }
  const confidenceValues = points.map((point) => {
    if (!point || typeof point !== 'object') {
      return 0;
    }
    const payload = point as { visibility?: unknown; presence?: unknown };
    const visibility = typeof payload.visibility === 'number' ? payload.visibility : undefined;
    const presence = typeof payload.presence === 'number' ? payload.presence : undefined;
    return clamp01(visibility ?? presence ?? 0);
  });
  const visiblePointCount = confidenceValues.filter((value) => value >= 0.5).length;
  return {
    timestampMs,
    confidence: roundMetric(average(confidenceValues)),
    visiblePointCount,
    totalPointCount: points.length,
    captureMetrics: deriveMediaPipePoseCaptureSample(points),
  };
}

export function createBrowserMediaPipePoseAdapter(
  options: BrowserMediaPipeAdapterOptions = {},
): LivePoseWindowAdapter {
  let detector: MediaPipePoseDetector | null = null;
  let loadPromise: Promise<MediaPipePoseDetector | null> | null = null;
  let status: LivePoseWindowAdapterStatus = { state: 'loading' };

  const loadDetector = async () => {
    if (detector) {
      return detector;
    }
    if (status.state === 'unavailable') {
      return null;
    }
    if (!loadPromise) {
      loadPromise = (async () => {
        try {
          const vision = await import('@mediapipe/tasks-vision');
          const filesetResolver = await vision.FilesetResolver.forVisionTasks(
            options.wasmAssetPath || '/mediapipe/tasks-vision/wasm',
          );
          detector = await vision.PoseLandmarker.createFromOptions(filesetResolver, {
            baseOptions: {
              modelAssetPath: options.modelAssetPath || '/mediapipe/models/pose_landmarker_lite.task',
            },
            runningMode: 'VIDEO',
            numPoses: 1,
          });
          status = { state: 'ready' };
          return detector;
        } catch (error) {
          status = {
            state: 'unavailable',
            reason: error instanceof Error ? error.message : 'mediapipe_pose_unavailable',
          };
          return null;
        }
      })();
    }
    return loadPromise;
  };

  return {
    provider: 'mediapipe_pose',
    getStatus: () => status,
    estimate: async (video, timestampMs) => {
      const activeDetector = await loadDetector();
      if (!activeDetector) {
        return null;
      }
      const result = activeDetector.detectForVideo(video, timestampMs) as Record<string, unknown>;
      const posePoints = Array.isArray(result?.landmarks) ? result.landmarks[0] : null;
      return summarizePoints(posePoints, timestampMs);
    },
    dispose: () => {
      detector?.close?.();
      detector = null;
      loadPromise = null;
      status = { state: 'loading' };
    },
  };
}

export function createLivePoseWindowAccumulator({
  liveSessionId,
  windowMs = DEFAULT_WINDOW_MS,
  maxSamples = DEFAULT_MAX_SAMPLES,
  metadata = {},
}: LivePoseWindowAccumulatorInput): {
  push: (sample: PoseSampleSummary) => MotionWindowSummary | null;
  flush: () => MotionWindowSummary | null;
  getSampleCount: () => number;
} {
  let samples: PoseSampleSummary[] = [];
  let windowStartMs: number | null = null;
  let sequence = 0;

  const buildSummary = (endMs: number): MotionWindowSummary | null => {
    if (windowStartMs === null || !samples.length) {
      return null;
    }
    const confidenceValues = samples.map((sample) => sample.confidence);
    const visibleRatios = samples.map((sample) => (
      sample.totalPointCount > 0 ? sample.visiblePointCount / sample.totalPointCount : 0
    ));
    const meanConfidence = roundMetric(average(confidenceValues));
    const meanVisibleRatio = roundMetric(average(visibleRatios));
    const windowId = `${liveSessionId}:window:${Math.round(windowStartMs)}:${sequence}`;
    sequence += 1;
    return {
      window_id: windowId,
      live_session_id: liveSessionId,
      ts_start_ms: windowStartMs,
      ts_end_ms: endMs,
      skeleton_family: 'mediapipe_pose_33',
      confidence_stats: {
        mean_confidence: meanConfidence,
        mean_visible_ratio: meanVisibleRatio,
        sample_count: samples.length,
      },
      scores: {
        pose_confidence: meanConfidence,
        body_visibility: meanVisibleRatio,
      },
      findings: meanConfidence < 0.4 || meanVisibleRatio < 0.4
        ? ['pose_visibility_low']
        : [],
      keypoint_frame_count: samples.length,
      metadata: {
        source: 'workspace_webrtc_receiver',
        window_ms: windowMs,
        max_samples: maxSamples,
        ...metadata,
        ...buildCaptureMotionWindowMetadata(samples),
      },
    };
  };

  const resetWindow = () => {
    samples = [];
    windowStartMs = null;
  };

  return {
    push: (sample) => {
      if (windowStartMs === null) {
        windowStartMs = sample.timestampMs;
      }
      if (samples.length < maxSamples) {
        samples.push({
          ...sample,
          confidence: clamp01(sample.confidence),
          visiblePointCount: Math.max(0, sample.visiblePointCount),
          totalPointCount: Math.max(0, sample.totalPointCount),
        });
      }
      if (sample.timestampMs - windowStartMs < windowMs) {
        return null;
      }
      const summary = buildSummary(sample.timestampMs);
      resetWindow();
      return summary;
    },
    flush: () => {
      const endMs = samples[samples.length - 1]?.timestampMs ?? windowStartMs ?? 0;
      const summary = buildSummary(endMs);
      resetWindow();
      return summary;
    },
    getSampleCount: () => samples.length,
  };
}

export function createLivePoseWindowController({
  video,
  liveSessionId,
  adapter = createBrowserMediaPipePoseAdapter(),
  appendMotionWindow,
  sampleFps = DEFAULT_SAMPLE_FPS,
  windowMs = DEFAULT_WINDOW_MS,
  maxSamples = DEFAULT_MAX_SAMPLES,
  scheduler = createDefaultScheduler(),
  now = createDefaultNow(),
  metadata = {},
  onStatus,
}: LivePoseWindowControllerInput): LivePoseWindowController {
  const minSampleIntervalMs = 1000 / Math.max(1, sampleFps);
  const accumulator = createLivePoseWindowAccumulator({
    liveSessionId,
    windowMs,
    maxSamples,
    metadata: {
      sample_fps_limit: sampleFps,
      ...metadata,
    },
  });
  let status: LivePoseWindowControllerStatus = {
    state: 'idle',
    appendedWindowCount: 0,
  };
  let frameHandle: number | null = null;
  let running = false;
  let sampleInFlight = false;
  let lastSampleAtMs = -Infinity;

  const updateStatus = (next: Partial<LivePoseWindowControllerStatus>) => {
    status = {
      ...status,
      ...next,
    };
    onStatus?.(status);
  };

  const stopFrame = () => {
    if (frameHandle !== null) {
      scheduler.cancelFrame(frameHandle);
      frameHandle = null;
    }
  };

  const stop = () => {
    running = false;
    stopFrame();
    adapter.dispose?.();
    if (status.state !== 'provider_unavailable' && status.state !== 'append_error') {
      updateStatus({ state: 'stopped' });
    }
  };

  const scheduleFrame = () => {
    stopFrame();
    if (!running) {
      return;
    }
    frameHandle = scheduler.requestFrame((timestamp) => {
      void processFrame(timestamp);
    });
  };

  const processFrame = async (timestamp: number) => {
    if (!running) {
      return;
    }
    scheduleFrame();
    const adapterStatus = adapter.getStatus?.();
    if (adapterStatus?.state === 'unavailable') {
      updateStatus({
        state: 'provider_unavailable',
        reason: adapterStatus.reason,
      });
      stop();
      return;
    }
    if (video.readyState < MIN_VIDEO_READY_STATE) {
      updateStatus({ state: 'waiting_video' });
      return;
    }
    const currentMs = Number.isFinite(timestamp) ? timestamp : now();
    if (currentMs - lastSampleAtMs < minSampleIntervalMs || sampleInFlight) {
      return;
    }
    lastSampleAtMs = currentMs;
    sampleInFlight = true;
    try {
      updateStatus({ state: 'active', reason: undefined });
      const sample = await adapter.estimate(video, currentMs);
      const nextAdapterStatus = adapter.getStatus?.();
      if (nextAdapterStatus?.state === 'unavailable') {
        updateStatus({
          state: 'provider_unavailable',
          reason: nextAdapterStatus.reason,
        });
        stop();
        return;
      }
      if (!sample) {
        return;
      }
      const summary = accumulator.push(sample);
      if (!summary) {
        return;
      }
      await appendMotionWindow(summary, now());
      updateStatus({
        state: 'active',
        appendedWindowCount: status.appendedWindowCount + 1,
        lastWindowId: summary.window_id,
      });
    } catch (error) {
      updateStatus({
        state: 'append_error',
        reason: error instanceof Error ? error.message : 'motion_window_append_failed',
      });
      stop();
    } finally {
      sampleInFlight = false;
    }
  };

  return {
    start: () => {
      if (running) {
        return;
      }
      running = true;
      updateStatus({ state: 'active' });
      scheduleFrame();
    },
    stop,
    getStatus: () => status,
  };
}
