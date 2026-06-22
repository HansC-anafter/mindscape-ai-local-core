import { CaptureRelayLauncherCard } from '../CaptureRelayLauncherCard';
import { ExternalProviderConnectionGuide } from '../ExternalProviderConnectionGuide';

export function ExternalProviderWizard({
  apiBase,
  bridgePayload,
  copyState,
  desktopDeviceLink,
  externalProviderActive,
  onCopy,
  pairingCode,
}: {
  apiBase: string;
  bridgePayload: string;
  copyState: 'idle' | 'copied' | 'failed';
  desktopDeviceLink: string;
  externalProviderActive: boolean;
  onCopy: (value: string) => void;
  pairingCode?: string;
}) {
  return (
    <div className="space-y-2">
      <ExternalProviderConnectionGuide />
      <CaptureRelayLauncherCard
        apiBase={apiBase}
        desktopDeviceLink={desktopDeviceLink}
        pairingCode={pairingCode}
      />
      <div
        className="rounded border border-gray-200 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-900"
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
        <div className="mt-2 grid grid-cols-1 gap-2">
          <button
            type="button"
            disabled={!pairingCode}
            onClick={() => onCopy(pairingCode || '')}
            className="rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
          >
            Copy code
          </button>
        </div>
        <details
          className="mt-2 rounded border border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-950"
          data-testid="external-provider-advanced-payload"
        >
          <summary className="cursor-pointer text-[11px] font-semibold text-gray-700 dark:text-gray-200">
            Advanced bridge payload
          </summary>
          <button
            type="button"
            disabled={!bridgePayload}
            onClick={() => onCopy(bridgePayload)}
            className="mt-2 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
            data-testid="external-provider-copy-payload"
          >
            Copy payload
          </button>
          <pre
            className="mt-2 max-h-28 overflow-auto rounded bg-gray-950 p-2 text-[10px] leading-4 text-gray-100"
            data-testid="external-provider-bridge-payload"
          >
            {bridgePayload || 'waiting for pairing code'}
          </pre>
        </details>
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
