'use client';

import React from 'react';
import { Camera, CheckCircle2, Loader2, Video, XCircle } from 'lucide-react';

import { DesktopSourcePicker } from '@/components/workspace/device-binding/DesktopSourcePicker';
import { DesktopSourcePreview } from '@/components/workspace/device-binding/DesktopSourcePreview';
import { CameraFacingModeToggle } from './CameraFacingModeToggle';
import { CaptureOrientationToggle } from './CaptureOrientationToggle';
import { CaptureFullscreenButton } from './CaptureFullscreenButton';
import { CaptureGuidanceOverlay } from './CaptureGuidanceOverlay';
import type { useDeviceLinkCaptureSession } from './useDeviceLinkCaptureSession';

type DeviceLinkCaptureSession = ReturnType<typeof useDeviceLinkCaptureSession>;

interface MobileCaptureCockpitProps {
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

export function MobileCaptureCockpit({ session }: MobileCaptureCockpitProps) {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <section
        ref={session.captureRootRef}
        className="relative flex min-h-screen flex-col overflow-hidden bg-black"
        data-testid="mobile-capture-cockpit"
      >
        <div className="absolute inset-0">
          {session.sourceMode === 'camera' ? (
            <div className="flex h-full items-center justify-center bg-gray-950 p-4">
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

        <div className="relative z-10 flex min-h-screen flex-col justify-between bg-gradient-to-b from-black/75 via-transparent to-black/85 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3 rounded-md border border-white/10 bg-black/35 px-3 py-2 backdrop-blur">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-white/10">
                <StatusIcon state={session.state} />
              </div>
              <div className="min-w-0">
                <h1 className="text-base font-semibold">Motion source</h1>
                <p className="truncate text-xs text-white/70">
                  {session.connectionStatusLabel} · {session.videoTrackLabel || session.mediaState}
                </p>
              </div>
            </div>
            <div className="rounded-md border border-white/10 bg-black/35 px-3 py-2 font-mono text-xs text-white/80 backdrop-blur">
              {session.pairingCode}
            </div>
          </div>

          <div className="mx-auto w-full max-w-lg space-y-3">
            <div className="grid grid-cols-2 gap-2 rounded-md border border-white/10 bg-black/45 p-1 backdrop-blur">
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
              <div className="rounded-md border border-white/10 bg-black/55 p-3 backdrop-blur">
                <DesktopSourcePicker
                  selectedDeviceId={session.selectedCamera?.deviceId}
                  onSelectionChange={session.setSelectedCamera}
                  disabled={session.active}
                />
              </div>
            ) : null}

            {session.message || session.connectionStatusDetail ? (
              <div
                className="rounded-md border border-white/10 bg-black/50 px-3 py-2 text-sm text-white/85 backdrop-blur"
                data-testid="device-link-connection-status-detail"
              >
                {session.message || session.connectionStatusDetail}
              </div>
            ) : null}
            {session.fullscreenMessage ? (
              <div className="rounded-md border border-amber-300/30 bg-amber-500/20 px-3 py-2 text-sm text-amber-50 backdrop-blur">
                {session.fullscreenMessage}
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
          </div>
        </div>
      </section>
    </main>
  );
}
