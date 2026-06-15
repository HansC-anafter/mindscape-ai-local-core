'use client';

import React from 'react';
import { Link2, Loader2, MonitorUp, Smartphone } from 'lucide-react';

import {
  CaptureSourceBridgeProvider,
  useOptionalCaptureSourceBridge,
  useCaptureSourceBridge,
} from './CaptureSourceBridgeProvider';
import { CaptureSourceList } from './CaptureSourceList';

export interface CaptureSourceRailProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
  showPreview?: boolean;
}

function CaptureSourceRailContent({
  showPreview = true,
}: {
  showPreview?: boolean;
}) {
  const {
    disabled,
    state,
    pairing,
    error,
    phonePublicOrigin,
    phoneReadiness,
    phoneDeviceLink,
    phoneQrCode,
    desktopDeviceLink,
    setPhonePublicOrigin,
    startPairing,
  } = useCaptureSourceBridge();

  React.useEffect(() => {
    if (state === 'idle' && !pairing && !disabled) {
      void startPairing();
    }
  }, [disabled, pairing, startPairing, state]);

  return (
    <div className="flex min-h-full flex-col gap-3 p-3 text-xs">
      <div className="rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900">
        <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          <Smartphone className="h-4 w-4 text-sky-500" aria-hidden="true" />
          Motion source
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400" data-testid="motion-source-rail-state">
          {state}
        </div>
      </div>

      {pairing ? (
        <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
          <div className="mb-2 flex items-center gap-1 font-mono text-sm font-semibold text-gray-900 dark:text-gray-100">
            <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
            {pairing.pairing_code}
          </div>
          <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
            <div className="mb-1 flex items-center gap-1 font-medium text-gray-800 dark:text-gray-100">
              <Smartphone className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
              Phone
            </div>
            <a
              href={phoneDeviceLink}
              target="_blank"
              rel="noreferrer"
              aria-label="Phone source link"
              className="block break-all text-xs text-sky-700 hover:text-sky-800 dark:text-sky-300"
            >
              {phoneDeviceLink}
            </a>
            <label className="mt-2 block">
              <span className="mb-1 block text-[10px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
                Phone HTTPS origin
              </span>
              <input
                value={phonePublicOrigin}
                onChange={(event) => setPhonePublicOrigin(event.target.value)}
                placeholder="https://192.168.x.x:8343"
                className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                data-testid="phone-public-origin-input"
              />
            </label>
            <div
              className={`mt-2 rounded border px-2 py-1 text-[11px] ${
                phoneReadiness.state === 'ready'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
                  : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
              }`}
              data-testid="phone-lan-readiness"
            >
              {phoneReadiness.message}
            </div>
            <div
              className="mt-2 rounded border border-gray-200 px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:text-gray-300"
              data-testid="phone-qr-readiness"
            >
              {phoneReadiness.qrReady
                ? 'QR-ready link: open this HTTPS link on the phone.'
                : 'QR blocked until a non-localhost HTTPS origin is configured.'}
            </div>
            {phoneQrCode ? (
              <div
                className="mt-2 flex justify-center rounded border border-gray-200 bg-white p-2 text-gray-950 dark:border-gray-800"
                data-testid="phone-qr-code"
              >
                <svg
                  role="img"
                  aria-label="Phone pairing QR code"
                  viewBox={`0 0 ${phoneQrCode.viewBoxSize} ${phoneQrCode.viewBoxSize}`}
                  className="h-48 w-48"
                  shapeRendering="crispEdges"
                >
                  <path d={phoneQrCode.path} fill="currentColor" />
                </svg>
              </div>
            ) : null}
          </div>
          <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
            <div className="mb-1 flex items-center gap-1 font-medium text-gray-800 dark:text-gray-100">
              <MonitorUp className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
              This computer / OBS
            </div>
            <a
              href={desktopDeviceLink}
              target="_blank"
              rel="noreferrer"
              aria-label="Desktop camera source link"
              className="block break-all text-xs text-sky-700 hover:text-sky-800 dark:text-sky-300"
            >
              {desktopDeviceLink}
            </a>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      ) : null}

      <CaptureSourceList showPreview={showPreview} />

      <button
        type="button"
        onClick={() => void startPairing()}
        disabled={disabled || state === 'creating'}
        className="mt-auto inline-flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-wait disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
      >
        {state === 'creating' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
        New pairing code
      </button>
    </div>
  );
}

export function CaptureSourceRail({
  apiUrl,
  workspaceId,
  disabled = false,
  showPreview = true,
}: CaptureSourceRailProps) {
  const existingBridge = useOptionalCaptureSourceBridge();

  if (existingBridge) {
    return <CaptureSourceRailContent showPreview={showPreview} />;
  }

  return (
    <CaptureSourceBridgeProvider
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      disabled={disabled}
    >
      <CaptureSourceRailContent showPreview={showPreview} />
    </CaptureSourceBridgeProvider>
  );
}

export default CaptureSourceRail;
