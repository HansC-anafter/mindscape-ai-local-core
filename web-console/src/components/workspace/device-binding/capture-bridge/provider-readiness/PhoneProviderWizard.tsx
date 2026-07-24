import { ExternalLink, Smartphone } from 'lucide-react';

import type { DeviceLinkReadiness } from '@/lib/media-transport/deviceLinkReadiness';
import type { QrCodeSvgPath } from '@/lib/media-transport/qrCode';

export function PhoneProviderWizard({
  phoneDeviceLink,
  phonePublicOrigin,
  phoneQrCode,
  phoneReadiness,
  setPhonePublicOrigin,
}: {
  phoneDeviceLink?: string;
  phonePublicOrigin: string;
  phoneQrCode?: QrCodeSvgPath | null;
  phoneReadiness: DeviceLinkReadiness;
  setPhonePublicOrigin: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
        <div className="mb-1 flex items-center gap-1 font-medium text-gray-800 dark:text-gray-100">
          <Smartphone className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
          Phone camera
        </div>
        <ol className="mb-2 space-y-1 text-[11px] leading-4 text-gray-600 dark:text-gray-300">
          <li><strong>1.</strong> Scan the QR code or open the secure phone link.</li>
          <li><strong>2.</strong> Aim the phone camera at your full body.</li>
          <li><strong>3.</strong> Tap Connect once and keep the page open.</li>
        </ol>
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
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] font-medium text-gray-600 dark:text-gray-300">
            Connection settings
          </summary>
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
        </details>
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
    </div>
  );
}
