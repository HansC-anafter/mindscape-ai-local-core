import React from 'react';

import type { DeviceLinkReadiness } from '@/lib/media-transport/deviceLinkReadiness';
import type { QrCodeSvgPath } from '@/lib/media-transport/qrCode';

import { DesktopProviderWizard } from './DesktopProviderWizard';
import { ExternalProviderWizard } from './ExternalProviderWizard';
import { PhoneProviderWizard } from './PhoneProviderWizard';
import { ProviderWizardFrame } from './ProviderWizardFrame';
import { buildExternalProviderBridgePayload } from './providerPayload';
import { MAX_ACTIVE_SOURCE_SLOTS, PROVIDER_RAIL_ITEMS, type ProviderId } from './providerRailItems';

export function ProviderReadinessBlock({
  activeSlotCount,
  apiBase,
  externalProviderActive,
  pairingCode,
  desktopDeviceLink,
  phoneDeviceLink,
  phonePublicOrigin,
  phoneQrCode,
  phoneReadiness,
  setPhonePublicOrigin,
  workspaceId,
}: {
  activeSlotCount: number;
  apiBase: string;
  externalProviderActive: boolean;
  desktopDeviceLink: string;
  pairingCode?: string;
  phoneDeviceLink?: string;
  phonePublicOrigin: string;
  phoneQrCode?: QrCodeSvgPath | null;
  phoneReadiness: DeviceLinkReadiness;
  setPhonePublicOrigin: (value: string) => void;
  workspaceId: string;
}) {
  const boundedActiveSlotCount = Math.min(activeSlotCount, MAX_ACTIVE_SOURCE_SLOTS);
  const [activeWizardId, setActiveWizardId] = React.useState<ProviderId | null>(null);
  const [copyState, setCopyState] = React.useState<'idle' | 'copied' | 'failed'>('idle');
  const activeProvider = PROVIDER_RAIL_ITEMS.find((provider) => provider.id === activeWizardId) || null;
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
        {PROVIDER_RAIL_ITEMS.map((provider) => {
          const isActiveProvider = activeWizardId === provider.id;
          return (
            <div
              key={provider.label}
              className={`rounded border px-2 py-1.5 ${
                isActiveProvider
                  ? 'border-sky-300 bg-sky-50 dark:border-sky-800 dark:bg-sky-950/30'
                  : 'border-gray-200 dark:border-gray-800'
              }`}
              data-active-provider={isActiveProvider ? 'true' : 'false'}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium text-gray-800 dark:text-gray-100">
                    {provider.label}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-gray-500 dark:text-gray-400">
                    {provider.summary}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span
                    className={
                      provider.readiness === 'ready'
                        ? 'rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200'
                        : 'rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
                    }
                  >
                    {provider.id === 'external' && externalProviderActive
                      ? 'Connected'
                      : provider.status}
                  </span>
                  <button
                    type="button"
                    onClick={() => setActiveWizardId(provider.id)}
                    className={`inline-flex h-8 w-8 items-center justify-center rounded-md border shadow-sm ${
                      isActiveProvider
                        ? 'border-sky-400 bg-sky-100 text-sky-800 dark:border-sky-700 dark:bg-sky-900/50 dark:text-sky-100'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900'
                    }`}
                    data-testid={`capture-provider-tool-${provider.id}`}
                    aria-label={`Open ${provider.label} setup`}
                    aria-pressed={isActiveProvider}
                  >
                    <provider.Icon className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {activeProvider ? (
        <ProviderWizardFrame
          title={activeProvider.label}
          onClose={() => setActiveWizardId(null)}
        >
          {activeProvider.id === 'phone' ? (
            <PhoneProviderWizard
              phoneDeviceLink={phoneDeviceLink}
              phonePublicOrigin={phonePublicOrigin}
              phoneQrCode={phoneQrCode}
              phoneReadiness={phoneReadiness}
              setPhonePublicOrigin={setPhonePublicOrigin}
            />
          ) : null}
          {activeProvider.id === 'desktop' ? (
            <DesktopProviderWizard
              desktopDeviceLink={desktopDeviceLink}
              pairingCode={pairingCode}
            />
          ) : null}
          {activeProvider.id === 'external' ? (
            <ExternalProviderWizard
              apiBase={apiBase}
              bridgePayload={bridgePayload}
              copyState={copyState}
              desktopDeviceLink={desktopDeviceLink}
              externalProviderActive={externalProviderActive}
              onCopy={(value) => void copyValue(value)}
              pairingCode={pairingCode}
            />
          ) : null}
        </ProviderWizardFrame>
      ) : null}
    </div>
  );
}
