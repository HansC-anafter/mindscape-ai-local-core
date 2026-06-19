'use client';

import React from 'react';
import { ExternalLink, Link2, Loader2, MonitorUp, Smartphone } from 'lucide-react';

import {
  CaptureSourceBridgeProvider,
  useOptionalCaptureSourceBridge,
  type CaptureSourceBridgeContextValue,
} from './CaptureSourceBridgeProvider';
import { CaptureSourceList } from './CaptureSourceList';

const MAX_ACTIVE_SOURCE_SLOTS = 3;

export interface CaptureSourceRailProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
  showPreview?: boolean;
}

type ProviderRailItem = {
  label: string;
  status: string;
  description: string;
  readiness: 'ready' | 'bridge_required';
};

const PROVIDER_RAIL_ITEMS: ProviderRailItem[] = [
  {
    label: 'Phone owned camera',
    status: 'Ready',
    description: 'Uses this phone or tablet camera through the browser device-link page.',
    readiness: 'ready',
  },
  {
    label: 'Computer / OBS camera',
    status: 'Ready',
    description: 'Uses desktop, USB, virtual camera, or OBS sources visible to the browser.',
    readiness: 'ready',
  },
  {
    label: 'External device provider',
    status: 'Bridge required',
    description: 'Use a neutral host/mobile bridge for DJI Ronin, RS, Osmo, or future provider devices.',
    readiness: 'bridge_required',
  },
];

function ExternalProviderConnectionGuide() {
  return (
    <div
      className="mt-2 rounded border border-sky-200 bg-sky-50/70 px-2 py-2 text-[11px] text-sky-900 dark:border-sky-900/70 dark:bg-sky-950/30 dark:text-sky-100"
      data-testid="external-provider-connection-guide"
    >
      <div className="font-semibold text-sky-950 dark:text-sky-50">
        External provider connection guide
      </div>
      <ol className="mt-1 space-y-1">
        <li>
          <span className="font-semibold">1. Start bridge:</span> run a neutral host/mobile bridge for DJI Ronin, RS, Osmo, or future provider devices.
        </li>
        <li>
          <span className="font-semibold">2. Pair source:</span> connect the bridge into the same device-link session; it consumes one of the 3 source slots.
        </li>
        <li>
          <span className="font-semibold">3. Monitor here:</span> once active, the provider feed appears in the active source list below.
        </li>
      </ol>
      <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-100">
        Do not use the Phone owned camera link for DJI provider control; that link only captures this phone camera.
      </div>
    </div>
  );
}

function ProviderReadinessBlock({ activeSlotCount }: { activeSlotCount: number }) {
  const boundedActiveSlotCount = Math.min(activeSlotCount, MAX_ACTIVE_SOURCE_SLOTS);

  return (
    <div
      className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950"
      data-testid="capture-provider-readiness-block"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Provider backends
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            Neutral source slots shared by all provider paths.
          </div>
        </div>
        <div
          className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200"
          data-testid="capture-provider-source-slot-count"
        >
          {boundedActiveSlotCount} / {MAX_ACTIVE_SOURCE_SLOTS} active
        </div>
      </div>
      <div className="space-y-1.5">
        {PROVIDER_RAIL_ITEMS.map((provider) => (
          <div
            key={provider.label}
            className="rounded border border-gray-200 px-2 py-1.5 dark:border-gray-800"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 truncate font-medium text-gray-800 dark:text-gray-100">
                {provider.label}
              </div>
              <span
                className={
                  provider.readiness === 'ready'
                    ? 'shrink-0 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200'
                    : 'shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
                }
              >
                {provider.status}
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
              {provider.description}
            </div>
          </div>
        ))}
      </div>
      <ExternalProviderConnectionGuide />
    </div>
  );
}

function CaptureSourceRailContent({
  bridge: controlledBridge = null,
  showPreview = true,
}: {
  bridge?: CaptureSourceBridgeContextValue | null;
  showPreview?: boolean;
}) {
  const contextBridge = useOptionalCaptureSourceBridge();
  const bridge = controlledBridge || contextBridge;

  if (!bridge) {
    throw new Error('CaptureSourceRailContent requires a CaptureSourceBridgeProvider or controlled bridge.');
  }

  const {
    disabled,
    state,
    pairing,
    sessions,
    error,
    phonePublicOrigin,
    phoneReadiness,
    phoneDeviceLink,
    phoneQrCode,
    desktopDeviceLink,
    setPhonePublicOrigin,
    startPairing,
  } = bridge;

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

      <ProviderReadinessBlock activeSlotCount={sessions.length} />

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
            {phoneDeviceLink ? (
              <a
                href={phoneDeviceLink}
                target="_blank"
                rel="noreferrer"
                aria-label="Phone source link"
                className="block break-all text-xs text-sky-700 hover:text-sky-800 dark:text-sky-300"
              >
                {phoneDeviceLink}
              </a>
            ) : (
              <div
                className="block text-xs text-gray-500 dark:text-gray-400"
                data-testid="phone-source-link-blocked"
              >
                Open the remote workbench over HTTPS, or configure a trusted LAN HTTPS origin.
              </div>
            )}
            <label className="mt-2 block">
              <span className="mb-1 block text-[10px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
                Phone capture origin override
              </span>
              <input
                value={phonePublicOrigin}
                onChange={(event) => setPhonePublicOrigin(event.target.value)}
                placeholder="optional: https://192.168.x.x:8343"
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
                ? 'QR-ready. Scan it from another device, or open the phone camera directly here.'
                : 'QR blocked until a non-localhost HTTPS origin is available.'}
            </div>
            {phoneReadiness.qrReady && phoneDeviceLink ? (
              <a
                href={phoneDeviceLink}
                aria-label="Open phone camera"
                className="mt-2 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-md bg-sky-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-sky-700"
                data-testid="phone-source-open-button"
              >
                <Smartphone className="h-4 w-4" aria-hidden="true" />
                Open phone camera
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            ) : null}
            {phoneQrCode ? (
              <div
                className="mt-2 flex justify-center rounded border border-gray-200 bg-white p-2 text-gray-950 dark:border-gray-800"
                data-testid="phone-qr-code"
              >
                <svg
                  role="img"
                  aria-label="Phone pairing QR code"
                  viewBox={`0 0 ${phoneQrCode.viewBoxSize} ${phoneQrCode.viewBoxSize}`}
                  className="h-40 w-40 sm:h-48 sm:w-48"
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

      <CaptureSourceList
        bridge={bridge}
        showPreview={showPreview}
      />

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

export function CaptureSourceRailFromBridge({
  bridge,
  showPreview = true,
}: {
  bridge: CaptureSourceBridgeContextValue;
  showPreview?: boolean;
}) {
  return (
    <CaptureSourceRailContent
      bridge={bridge}
      showPreview={showPreview}
    />
  );
}

export default CaptureSourceRail;
