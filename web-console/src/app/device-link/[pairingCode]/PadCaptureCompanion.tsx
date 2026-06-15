'use client';

import React from 'react';
import { BookOpen, Camera, CheckCircle2, Loader2, Video, XCircle } from 'lucide-react';

import { DesktopSourcePicker } from '@/components/workspace/device-binding/DesktopSourcePicker';
import { DesktopSourcePreview } from '@/components/workspace/device-binding/DesktopSourcePreview';
import { CameraFacingModeToggle } from './CameraFacingModeToggle';
import { CaptureOrientationToggle } from './CaptureOrientationToggle';
import { CaptureFullscreenButton } from './CaptureFullscreenButton';
import { CaptureGuidanceOverlay } from './CaptureGuidanceOverlay';
import type { ReferenceLessonState, useDeviceLinkCaptureSession } from './useDeviceLinkCaptureSession';

type DeviceLinkCaptureSession = ReturnType<typeof useDeviceLinkCaptureSession>;

interface PadCaptureCompanionProps {
  session: DeviceLinkCaptureSession;
}

function StatusIcon({ state }: { state: DeviceLinkCaptureSession['state'] }) {
  if (state === 'paired') {
    return <CheckCircle2 className="h-5 w-5 text-emerald-300" aria-hidden="true" />;
  }
  if (state === 'streaming') {
    return <Video className="h-5 w-5 text-emerald-300" aria-hidden="true" />;
  }
  if (state === 'error' || state === 'closed' || state === 'secure_context_required') {
    return <XCircle className="h-5 w-5 text-rose-300" aria-hidden="true" />;
  }
  return <Camera className="h-5 w-5 text-sky-300" aria-hidden="true" />;
}

function formatTimestamp(timestampMs?: number): string {
  if (typeof timestampMs !== 'number' || Number.isNaN(timestampMs)) {
    return 'No timestamp';
  }
  const totalSeconds = Math.max(0, Math.floor(timestampMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function ReferenceLessonPanel({ state }: { state: ReferenceLessonState | null }) {
  return (
    <aside className="flex min-h-0 flex-col rounded-lg border border-white/10 bg-white/[0.04] p-4">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-sky-500/15 text-sky-100">
          <BookOpen className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">Reference lesson</h2>
          <p className="text-sm text-white/55">Compact state from desktop workbench</p>
        </div>
      </div>
      <div className="mb-4 aspect-video overflow-hidden rounded-md border border-white/10 bg-black">
        {state?.poster_ref ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={state.poster_ref} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-white/45">
            Waiting for the desktop lesson reference.
          </div>
        )}
      </div>
      <div className="space-y-3">
        <div>
          <div className="text-xs uppercase tracking-normal text-white/45">Chapter</div>
          <div className="text-base font-semibold">{state?.title || state?.chapter_ref || 'No active chapter'}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-normal text-white/45">Timestamp</div>
          <div className="font-mono text-sm text-white/80">{formatTimestamp(state?.timestamp_ms)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-normal text-white/45">Focus cue</div>
          <div className="text-sm text-white/80">{state?.focus_cue || 'Keep your body centered while waiting for the next cue.'}</div>
        </div>
      </div>
    </aside>
  );
}

export function PadCaptureCompanion({ session }: PadCaptureCompanionProps) {
  return (
    <main className="min-h-screen bg-gray-950 p-4 text-white">
      <section
        ref={session.captureRootRef}
        className="grid min-h-[calc(100vh-2rem)] grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)] gap-4"
        data-testid="pad-capture-companion"
      >
        <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-black">
          <header className="flex items-center justify-between gap-3 border-b border-white/10 bg-gray-950/95 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-white/10">
                <StatusIcon state={session.state} />
              </div>
              <div className="min-w-0">
                <h1 className="text-lg font-semibold">Capture companion</h1>
                <p className="truncate text-sm text-white/55">
                  {session.connectionStatusLabel} · {session.videoTrackLabel || session.mediaState}
                </p>
              </div>
            </div>
            <div className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 font-mono text-xs text-white/70">
              {session.pairingCode}
            </div>
          </header>

          <div className="relative min-h-0 flex-1">
            {session.sourceMode === 'camera' ? (
              <div className="flex h-full items-center justify-center p-4">
                <DesktopSourcePreview
                  stream={session.localStream}
                  sourceKind={session.selectedCameraKind}
                  state={session.mediaState}
                  error={session.state === 'error' ? session.message : null}
                />
              </div>
            ) : (
              <video
                ref={session.videoRef}
                className="h-full w-full bg-black object-cover"
                autoPlay
                playsInline
                muted
                data-testid="device-link-local-preview"
              />
            )}
            <CaptureGuidanceOverlay
              captureOrientation={session.captureOrientation}
              facingMode={session.phoneFacingMode}
              linkState={session.state}
              mediaState={session.mediaState}
              sourceMode={session.sourceMode}
              hasStream={Boolean(session.localStream)}
            />
          </div>

          <footer className="space-y-3 border-t border-white/10 bg-gray-950/95 p-4">
            <div className="grid grid-cols-2 gap-2 rounded-md border border-white/10 bg-black/45 p-1">
              {([
                ['phone', 'Phone'],
                ['camera', 'Camera'],
              ] as const).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => session.setSourceMode(mode)}
                  disabled={session.active}
                  className={`min-h-10 rounded px-3 py-2 text-sm font-semibold transition-colors ${
                    session.sourceMode === mode
                      ? 'bg-sky-500 text-white'
                      : 'text-white/75 hover:bg-white/10'
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  {label}
                </button>
              ))}
            </div>

            {session.sourceMode === 'camera' ? (
              <div className="rounded-md border border-white/10 bg-white/[0.04] p-3">
                <DesktopSourcePicker
                  selectedDeviceId={session.selectedCamera?.deviceId}
                  onSelectionChange={session.setSelectedCamera}
                  disabled={session.active}
                />
              </div>
            ) : null}

            {session.message || session.fullscreenMessage || session.connectionStatusDetail ? (
              <div
                className="rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white/80"
                data-testid="device-link-connection-status-detail"
              >
                {session.message || session.fullscreenMessage || session.connectionStatusDetail}
              </div>
            ) : null}

            <div className="grid grid-cols-[auto_auto_auto_1fr] gap-2">
              {session.sourceMode === 'phone' ? (
                <CameraFacingModeToggle
                  disabled={session.state === 'connecting' || session.captureControlBusy}
                  facingMode={session.phoneFacingMode}
                  onFlip={session.flipPhoneCamera}
                  busy={session.captureControlState === 'switching_camera'}
                />
              ) : null}
              {session.sourceMode === 'phone' ? (
                <CaptureOrientationToggle
                  disabled={session.state === 'connecting' || session.captureControlBusy}
                  orientation={session.captureOrientation}
                  onToggle={session.toggleCaptureOrientation}
                  busy={session.captureControlState === 'switching_orientation'}
                />
              ) : null}
              <CaptureFullscreenButton
                disabled={session.captureControlBusy && session.captureControlState !== 'fullscreen'}
                isFullscreen={session.isFullscreen}
                onToggle={session.toggleFullscreen}
                busy={session.captureControlState === 'fullscreen'}
              />
              <button
                type="button"
                onClick={session.connect}
                disabled={!session.canConnect}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-sky-500 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
              >
                {session.state === 'connecting' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                {session.connectButtonLabel}
              </button>
            </div>
          </footer>
        </div>

        <ReferenceLessonPanel state={session.referenceLessonState} />
      </section>
    </main>
  );
}
