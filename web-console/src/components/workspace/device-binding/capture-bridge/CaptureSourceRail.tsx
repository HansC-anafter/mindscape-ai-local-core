'use client';

import React from 'react';
import { ExternalLink, Link2, Loader2, MonitorUp, Smartphone } from 'lucide-react';

import {
  CaptureSourceBridgeProvider,
  useOptionalCaptureSourceBridge,
  type CaptureSourceBridgeContextValue,
} from './CaptureSourceBridgeProvider';
import { CaptureSourceList } from './CaptureSourceList';
import { buildDeviceControlWebSocketUrl } from '@/lib/device-binding/deviceBindingClient';

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
    description: 'Connect a provider bridge with the pairing code below.',
    readiness: 'bridge_required',
  },
];

function buildExternalProviderBridgePayload({
  apiBase,
  pairingCode,
  workspaceId,
}: {
  apiBase: string;
  pairingCode: string;
  workspaceId: string;
}): string {
  return JSON.stringify({
    transport: 'device_binding_control_ws',
    api_base: apiBase,
    workspace_id: workspaceId,
    pairing_code: pairingCode,
    control_ws_url: buildDeviceControlWebSocketUrl({ apiBase, workspaceId, pairingCode }),
    source_join: {
      type: 'source_join',
      display_name: 'External provider bridge',
      source_types: ['external_provider_camera'],
      metadata: {
        capture_surface: 'external_provider_bridge',
      },
    },
  }, null, 2);
}

function ProviderReadinessBlock({
  activeSlotCount,
  apiBase,
  externalProviderActive,
  pairingCode,
  workspaceId,
}: {
  activeSlotCount: number;
  apiBase: string;
  externalProviderActive: boolean;
  pairingCode?: string;
  workspaceId: string;
}) {
  const boundedActiveSlotCount = Math.min(activeSlotCount, MAX_ACTIVE_SOURCE_SLOTS);
  const [copyState, setCopyState] = React.useState<'idle' | 'copied' | 'failed'>('idle');
  const bridgePayload = pairingCode
    ? buildExternalProviderBridgePayload({ apiBase, pairingCode, workspaceId })
    : '';
  async function copyValue(value: string) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1600);
    } catch {
      setCopyState('failed');
    }
  }

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
                {provider.label === 'External device provider' && externalProviderActive
                  ? 'Connected'
                  : provider.status}
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
              {provider.description}
            </div>
          </div>
        ))}
      </div>
      <div
        className="mt-2 rounded border border-gray-200 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-900"
        data-testid="external-provider-bridge-card"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="font-semibold text-gray-900 dark:text-gray-100">
            External bridge
          </div>
          <span
            className={
              externalProviderActive
                ? 'rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200'
                : 'rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
            }
          >
            {externalProviderActive ? 'Connected' : 'Waiting'}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">Pairing</span>
          <span
            className="font-mono text-gray-900 dark:text-gray-100"
            data-testid="external-provider-pairing-code"
          >
            {pairingCode || 'creating...'}
          </span>
          <span className="text-gray-500 dark:text-gray-400">Source</span>
          <span className="font-mono text-gray-900 dark:text-gray-100">
            external_provider_camera
          </span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={!pairingCode}
            onClick={() => void copyValue(pairingCode || '')}
            className="rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
          >
            Copy code
          </button>
          <button
            type="button"
            disabled={!bridgePayload}
            onClick={() => void copyValue(bridgePayload)}
            className="rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
            data-testid="external-provider-copy-payload"
          >
            Copy payload
          </button>
        </div>
        <pre
          className="mt-2 max-h-28 overflow-auto rounded bg-gray-950 p-2 text-[10px] leading-4 text-gray-100"
          data-testid="external-provider-bridge-payload"
        >
          {bridgePayload || 'waiting for pairing code'}
        </pre>
        {copyState === 'copied' ? (
          <div className="mt-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-200">
            Copied.
          </div>
        ) : null}
        {copyState === 'failed' ? (
          <div className="mt-1 text-[11px] font-semibold text-amber-700 dark:text-amber-200">
            Copy failed.
          </div>
        ) : null}
      </div>
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
    apiUrl,
    disabled,
    workspaceId,
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

      <ProviderReadinessBlock
        activeSlotCount={sessions.length}
        apiBase={apiUrl}
        externalProviderActive={sessions.some((session) => (
          session.source_types.includes('external_provider_camera')
        ))}
        pairingCode={pairing?.pairing_code}
        workspaceId={workspaceId}
      />

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
