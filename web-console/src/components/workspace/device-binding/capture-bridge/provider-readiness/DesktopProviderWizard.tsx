import { MonitorUp } from 'lucide-react';

export function DesktopProviderWizard({
  desktopDeviceLink,
  pairingCode,
}: {
  desktopDeviceLink: string;
  pairingCode?: string;
}) {
  return (
    <div className="space-y-2">
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
      <ol className="space-y-1 rounded border border-gray-200 bg-gray-50 p-2 text-[11px] leading-4 text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
        <li>1. Open the computer source link.</li>
        <li>2. Select a USB camera, virtual camera, or OBS Virtual Camera in the browser prompt.</li>
        <li>3. Return to the pack workbench after the source becomes active.</li>
      </ol>
      <div className="rounded border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
        Pairing code: <span className="font-mono text-gray-900 dark:text-gray-100">{pairingCode || 'creating...'}</span>.
      </div>
    </div>
  );
}
