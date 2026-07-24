'use client';

import { deriveMediaPipePoseCaptureSample } from './captureMotionMetrics';
import type {
  LivePoseWindowAdapter,
  LivePoseWindowAdapterStatus,
  PoseSampleSummary,
} from './livePoseWindow';

type BrowserMediaPipeAdapterOptions = {
  wasmAssetPath?: string;
  modelAssetPath?: string;
};

type MediaPipePoseDetector = {
  detectForVideo: (video: HTMLVideoElement, timestampMs: number) => unknown;
  close?: () => void;
};

const MEDIAPIPE_LOAD_RETRY_DELAY_MS = 1800;
const MAX_MEDIAPIPE_LOAD_RETRY_DELAY_MS = 9000;

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

function readMediaPipeLoadNowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function isRetriableMediaPipeLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error || '');
  return /chunk|timeout|network|failed to fetch|load failed|script error/i.test(message);
}

function formatMediaPipeLoadReason(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error || '');
  return message || 'mediapipe_pose_load_failed';
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

export function createUnavailablePoseAdapter(reason: string): LivePoseWindowAdapter {
  return {
    provider: 'mediapipe_pose',
    getStatus: () => ({ state: 'unavailable', reason }),
    estimate: async () => null,
  };
}

export function createBrowserMediaPipePoseAdapter(
  options: BrowserMediaPipeAdapterOptions = {},
): LivePoseWindowAdapter {
  let detector: MediaPipePoseDetector | null = null;
  let loadPromise: Promise<MediaPipePoseDetector | null> | null = null;
  let status: LivePoseWindowAdapterStatus = { state: 'loading' };
  let loadFailureCount = 0;
  let nextRetryAtMs = 0;

  const loadDetector = async () => {
    if (detector) {
      return detector;
    }
    if (status.state === 'unavailable') {
      return null;
    }
    const nowMs = readMediaPipeLoadNowMs();
    if (nextRetryAtMs > nowMs) {
      return null;
    }
    if (!loadPromise) {
      status = status.reason
        ? { state: 'loading', reason: status.reason }
        : { state: 'loading' };
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
          loadFailureCount = 0;
          nextRetryAtMs = 0;
          status = { state: 'ready' };
          return detector;
        } catch (error) {
          loadPromise = null;
          if (isRetriableMediaPipeLoadError(error)) {
            loadFailureCount += 1;
            const retryDelayMs = Math.min(
              MAX_MEDIAPIPE_LOAD_RETRY_DELAY_MS,
              MEDIAPIPE_LOAD_RETRY_DELAY_MS * loadFailureCount,
            );
            nextRetryAtMs = readMediaPipeLoadNowMs() + retryDelayMs;
            status = {
              state: 'loading',
              reason: `retrying_mediapipe_pose_load: ${formatMediaPipeLoadReason(error)}`,
            };
            return null;
          }
          status = {
            state: 'unavailable',
            reason: formatMediaPipeLoadReason(error),
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

