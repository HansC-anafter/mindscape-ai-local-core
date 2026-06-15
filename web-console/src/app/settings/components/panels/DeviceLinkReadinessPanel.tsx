'use client';

import React from 'react';
import { Camera, CheckCircle2, ExternalLink, Settings, ShieldCheck } from 'lucide-react';

interface DeviceLinkReadinessPanelProps {
  workspaceId?: string;
}

const composeCommand = [
  "DEVICE_LINK_PUBLIC_ORIGIN='https://<lan-ip>:8343'",
  "DEVICE_LINK_HTTPS_CERT_HOST_FILE='/path/to/lan-trusted-cert.pem'",
  "DEVICE_LINK_HTTPS_KEY_HOST_FILE='/path/to/lan-trusted-key.pem'",
  "DEVICE_LINK_HTTPS_HOST_PORT='8343'",
  'docker compose -f docker-compose.yml -f docker-compose.device-link-https.yml up -d frontend',
].join(' ');

const readinessCommand = 'node web-console/dev-proxy/device-link-https-readiness.mjs';

function StatusRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
      <div className="text-[11px] font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-1 text-sm font-medium text-gray-900 dark:text-gray-100">
        {value}
      </div>
    </div>
  );
}

export function DeviceLinkReadinessPanel({ workspaceId }: DeviceLinkReadinessPanelProps) {
  const motionSourceHref = workspaceId
    ? `/workspaces/${encodeURIComponent(workspaceId)}?tool=motion_source`
    : null;

  return (
    <div className="space-y-4" data-testid="device-link-readiness-panel">
      <section className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
        <div className="mb-3 flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-sky-500" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Device Link readiness</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Local-core owns device pairing, LAN HTTPS, QR readiness, and camera source transport.
            </p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <StatusRow label="Tool rail" value="Motion Source owns pairing" />
          <StatusRow label="Pack workbench" value="Yoga/Dance owns practice" />
          <StatusRow label="Phone/iPad QR" value="Requires trusted LAN HTTPS" />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
            <Settings className="h-4 w-4 text-sky-500" aria-hidden="true" />
            Local-core setup path
          </div>
          <ol className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <li>1. Use a LAN-reachable HTTPS origin, for example <code className="rounded bg-gray-100 px-1 dark:bg-gray-900">https://192.168.x.x:8343</code>.</li>
            <li>2. Use a certificate trusted by the phone or iPad, with SAN matching the LAN host.</li>
            <li>3. Start the existing device-link HTTPS compose overlay.</li>
            <li>4. Run the readiness CLI and continue only when it returns <code className="rounded bg-gray-100 px-1 dark:bg-gray-900">ready_for_phone_smoke=true</code>.</li>
          </ol>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
            <Camera className="h-4 w-4 text-sky-500" aria-hidden="true" />
            Product handoff
          </div>
          <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <li>Device setup stays in Settings and the workspace Motion Source rail.</li>
            <li>YogaCoach and DanceCoach workbenches consume the active source to start guided practice.</li>
            <li>Domain feedback, chapter matching, and practice reports stay inside the pack workbench.</li>
          </ul>
          {motionSourceHref ? (
            <a
              href={motionSourceHref}
              className="mt-3 inline-flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
            >
              Open Motion Source rail
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          ) : null}
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          Verification commands
        </div>
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">Start HTTPS device link</div>
            <code className="block rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200">
              {composeCommand}
            </code>
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">Readiness CLI</div>
            <code className="block rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200">
              {readinessCommand}
            </code>
          </div>
        </div>
      </section>
    </div>
  );
}

export default DeviceLinkReadinessPanel;
