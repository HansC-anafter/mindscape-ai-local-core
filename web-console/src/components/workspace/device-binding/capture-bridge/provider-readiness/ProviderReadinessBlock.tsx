import React from 'react';
import { ArrowRight, Smartphone } from 'lucide-react';

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
  const secondaryProviders = PROVIDER_RAIL_ITEMS.filter((provider) => provider.id !== 'phone');
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
            Choose a camera
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            Start with your phone, or connect another camera source.
          </div>
        </div>
        <div
          className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200"
          data-testid="capture-provider-source-slot-count"
        >
          {boundedActiveSlotCount} connected
        </div>
      </div>
      <button
        type="button"
        onClick={() => setActiveWizardId('phone')}
        className={`mb-2 flex min-h-14 w-full items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors ${
          activeWizardId === 'phone'
            ? 'border-sky-400 bg-sky-50 dark:border-sky-700 dark:bg-sky-950/40'
            : 'border-sky-200 bg-sky-50/70 hover:border-sky-400 hover:bg-sky-50 dark:border-sky-900 dark:bg-sky-950/20 dark:hover:border-sky-700'
        }`}
        data-testid="capture-provider-tool-phone"
        aria-label="Set up phone camera"
        aria-pressed={activeWizardId === 'phone'}
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-sky-600 text-white">
          <Smartphone className="h-4 w-4" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-gray-900 dark:text-gray-100">
            Use phone camera
          </span>
          <span className="block text-[11px] text-gray-600 dark:text-gray-300">
            Scan the QR code, then tap Connect once on your phone.
          </span>
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-sky-700 dark:text-sky-200">
          Set up
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      </button>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        Other camera sources
      </div>
      <div className="space-y-1.5">
        {secondaryProviders.map((provider) => {
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
                    className={`inline-flex min-h-8 items-center justify-center gap-1.5 rounded-md border px-2 text-[11px] font-semibold shadow-sm ${
                      isActiveProvider
                        ? 'border-sky-400 bg-sky-100 text-sky-800 dark:border-sky-700 dark:bg-sky-900/50 dark:text-sky-100'
                        : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900'
                    }`}
                    data-testid={`capture-provider-tool-${provider.id}`}
                    aria-label={`Set up ${provider.label}`}
                    aria-pressed={isActiveProvider}
                  >
                    <provider.Icon className="h-4 w-4" aria-hidden="true" />
                    Set up
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
