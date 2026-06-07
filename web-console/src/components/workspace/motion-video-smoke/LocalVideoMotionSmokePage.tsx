'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, FileVideo, Play, Square } from 'lucide-react';

import {
  createBrowserMediaPipePoseAdapter,
  createLivePoseWindowController,
  type LivePoseWindowController,
  type LivePoseWindowControllerStatus,
} from '@/lib/motion-analysis/livePoseWindow';
import { appendMotionWindow } from '@/lib/motion-analysis/motionWindowClient';
import {
  buildLocalVideoCaptureSessionId,
  buildLocalVideoMotionResourcePolicy,
  readLocalVideoLiveSessionId,
  registerLocalVideoLiveSession,
} from './localVideoMotionSmokeSession';

interface LocalVideoMotionSmokePageProps {
  workspaceId: string;
  apiUrl?: string;
}

type SmokeState = 'idle' | 'ready' | 'starting' | 'running' | 'stopped' | 'error';

const initialMotionStatus: LivePoseWindowControllerStatus = {
  state: 'idle',
  appendedWindowCount: 0,
};

export function LocalVideoMotionSmokePage({
  workspaceId,
  apiUrl = '',
}: LocalVideoMotionSmokePageProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const motionControllerRef = useRef<LivePoseWindowController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [objectUrl, setObjectUrl] = useState('');
  const [liveSessionId, setLiveSessionId] = useState<string | null>(null);
  const [state, setState] = useState<SmokeState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [motionStatus, setMotionStatus] = useState<LivePoseWindowControllerStatus>(initialMotionStatus);

  const stopMotion = useCallback(() => {
    motionControllerRef.current?.stop();
    motionControllerRef.current = null;
    if (videoRef.current) {
      videoRef.current.pause();
    }
    setState((current) => (current === 'running' || current === 'starting' ? 'stopped' : current));
  }, []);

  const releaseObjectUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  useEffect(() => () => {
    stopMotion();
    releaseObjectUrl();
  }, [releaseObjectUrl, stopMotion]);

  const selectFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] || null;
    stopMotion();
    releaseObjectUrl();
    setError(null);
    setLiveSessionId(null);
    setMotionStatus(initialMotionStatus);
    if (!nextFile) {
      setFile(null);
      setObjectUrl('');
      setState('idle');
      return;
    }
    const nextObjectUrl = URL.createObjectURL(nextFile);
    objectUrlRef.current = nextObjectUrl;
    setFile(nextFile);
    setObjectUrl(nextObjectUrl);
    setState('ready');
  };

  const fileDescriptor = useMemo(() => {
    if (!file) {
      return null;
    }
    return {
      name: file.name,
      size: file.size,
      type: file.type,
      lastModified: file.lastModified,
    };
  }, [file]);

  const startSmoke = async () => {
    if (!fileDescriptor || !videoRef.current) {
      return;
    }
    stopMotion();
    setError(null);
    setState('starting');
    try {
      const liveSessionPayload = await registerLocalVideoLiveSession({
        apiUrl,
        workspaceId,
        file: fileDescriptor,
      });
      const nextLiveSessionId = readLocalVideoLiveSessionId(liveSessionPayload);
      if (!nextLiveSessionId) {
        throw new Error('motion_runtime_live_session_missing');
      }
      setLiveSessionId(nextLiveSessionId);
      const controller = createLivePoseWindowController({
        video: videoRef.current,
        liveSessionId: nextLiveSessionId,
        adapter: createBrowserMediaPipePoseAdapter(),
        appendMotionWindow: async (summary, receivedAtMs) => {
          await appendMotionWindow({
            apiUrl,
            summary,
            receivedAtMs,
          });
        },
        metadata: {
          workspace_id: workspaceId,
          source_kind: 'local_video_file',
          capture_session_id: buildLocalVideoCaptureSessionId(fileDescriptor),
          resource_policy: buildLocalVideoMotionResourcePolicy(),
        },
        onStatus: setMotionStatus,
      });
      motionControllerRef.current = controller;
      await videoRef.current.play().catch(() => undefined);
      controller.start();
      setState('running');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'local_video_motion_smoke_failed');
      setState('error');
    }
  };

  const statusLabel = motionStatus.reason
    ? `${motionStatus.state}: ${motionStatus.reason}`
    : motionStatus.state;

  return (
    <main className="min-h-screen bg-neutral-950 px-6 py-6 text-neutral-100">
      <div className="mx-auto flex max-w-5xl flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800 pb-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">Local Video Motion Smoke</h1>
            <p className="mt-1 text-sm text-neutral-400">Workspace {workspaceId}</p>
          </div>
          <div className="rounded border border-neutral-700 px-3 py-2 text-sm text-neutral-300">
            {state}
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="overflow-hidden rounded-md border border-neutral-800 bg-black">
            <video
              ref={videoRef}
              className="aspect-video h-auto w-full bg-black object-contain"
              src={objectUrl || undefined}
              controls
              muted
              playsInline
              onPause={() => {
                if (state === 'running') {
                  stopMotion();
                }
              }}
              data-testid="local-video-motion-smoke-video"
            />
          </div>

          <aside className="flex flex-col gap-3 rounded-md border border-neutral-800 bg-neutral-900 p-4">
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded border border-neutral-700 px-3 py-3 text-sm font-medium hover:border-neutral-500">
              <FileVideo className="h-4 w-4" aria-hidden="true" />
              <span>Select local video</span>
              <input
                className="sr-only"
                type="file"
                accept="video/*"
                onChange={selectFile}
                data-testid="local-video-motion-smoke-file"
              />
            </label>

            <div className="rounded border border-neutral-800 bg-neutral-950 p-3 text-sm">
              <div className="text-xs uppercase tracking-wide text-neutral-500">Selected file</div>
              <div className="mt-1 break-words text-neutral-200">{file?.name || 'none'}</div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded border border-emerald-600 px-3 py-2 text-sm font-medium text-emerald-200 disabled:cursor-not-allowed disabled:border-neutral-700 disabled:text-neutral-500"
                disabled={!file || state === 'starting' || state === 'running'}
                onClick={() => void startSmoke()}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                Start
              </button>
              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 rounded border border-neutral-700 px-3 py-2 text-sm font-medium text-neutral-200 disabled:cursor-not-allowed disabled:text-neutral-500"
                disabled={state !== 'running' && state !== 'starting'}
                onClick={stopMotion}
              >
                <Square className="h-4 w-4" aria-hidden="true" />
                Stop
              </button>
            </div>

            <div className="rounded border border-neutral-800 bg-neutral-950 p-3 text-sm">
              <div className="mb-2 flex items-center gap-2 text-neutral-300">
                <Activity className="h-4 w-4" aria-hidden="true" />
                <span>Motion analysis</span>
              </div>
              <dl className="space-y-2 text-xs text-neutral-400">
                <div className="flex justify-between gap-3">
                  <dt>Status</dt>
                  <dd className="text-right text-neutral-200" data-testid="local-video-motion-smoke-status">
                    {statusLabel}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Live session</dt>
                  <dd className="max-w-[12rem] truncate text-right text-neutral-200">
                    {liveSessionId || 'none'}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Windows</dt>
                  <dd className="text-right text-neutral-200">{motionStatus.appendedWindowCount}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Last window</dt>
                  <dd className="max-w-[12rem] truncate text-right text-neutral-200">
                    {motionStatus.lastWindowId || 'none'}
                  </dd>
                </div>
              </dl>
            </div>

            {error && (
              <div className="rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-100">
                {error}
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
}

export default LocalVideoMotionSmokePage;
