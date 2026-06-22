'use client';

import React from 'react';
import { Loader2, Smartphone } from 'lucide-react';

import {
  CaptureSourceBridgeProvider,
  useOptionalCaptureSourceBridge,
  type CaptureSourceBridgeContextValue,
} from './CaptureSourceBridgeProvider';
import { CaptureSourceList } from './CaptureSourceList';
import { ProviderReadinessBlock } from './provider-readiness/ProviderReadinessBlock';

export interface CaptureSourceRailProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
  showPreview?: boolean;
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
        desktopDeviceLink={desktopDeviceLink}
        pairingCode={pairing?.pairing_code}
        phoneDeviceLink={phoneDeviceLink}
        phonePublicOrigin={phonePublicOrigin}
        phoneQrCode={phoneQrCode}
        phoneReadiness={phoneReadiness}
        setPhonePublicOrigin={setPhonePublicOrigin}
        workspaceId={workspaceId}
      />

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
