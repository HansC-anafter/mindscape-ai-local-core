'use client';

import React from 'react';
import { Clipboard, RadioTower } from 'lucide-react';

const DEFAULT_PUBLIC_RTMP_INGEST_ORIGIN = (
  process.env.NEXT_PUBLIC_CAMERA_CAPTURE_RTMP_ORIGIN || 'rtmp://34.80.219.221:1935'
);

function normalizeOrigin(value: string): string {
  return value.trim().replace(/\/+$/, '') || DEFAULT_PUBLIC_RTMP_INGEST_ORIGIN;
}

function normalizeStreamName(value: string): string {
  return value.trim().replace(/^\/+/, '') || 'external-camera';
}

export function buildPublicRtmpIngestUrl(origin: string, streamName: string): string {
  return `${normalizeOrigin(origin)}/${normalizeStreamName(streamName)}`;
}

function CopyField({
  label,
  value,
  onCopy,
}: {
  label: string;
  value: string;
  onCopy: (value: string) => void;
}) {
  return (
    <div className="rounded border border-sky-200 bg-white p-2 dark:border-sky-900 dark:bg-gray-950">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-normal text-sky-700 dark:text-sky-200">
        {label}
      </div>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all text-[11px] text-gray-900 dark:text-gray-100">
          {value}
        </code>
        <button
          type="button"
          onClick={() => onCopy(value)}
          className="shrink-0 rounded border border-sky-300 p-1 text-sky-700 hover:bg-sky-50 dark:border-sky-800 dark:text-sky-200 dark:hover:bg-sky-950"
          aria-label={`Copy ${label}`}
        >
          <Clipboard className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export function PublicRtmpIngestPanel({
  streamName,
  onCopy,
}: {
  streamName: string;
  onCopy: (value: string) => void;
}) {
  const [origin, setOrigin] = React.useState(DEFAULT_PUBLIC_RTMP_INGEST_ORIGIN);
  const publicRtmpUrl = buildPublicRtmpIngestUrl(origin, streamName);

  return (
    <div
      className="mt-2 rounded border border-sky-200 bg-sky-50 p-2 text-[11px] leading-4 text-sky-950 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100"
      data-testid="public-rtmp-ingest-panel"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1 font-semibold">
            <RadioTower className="h-3.5 w-3.5" aria-hidden="true" />
            Public RTMP push-stream
          </div>
          <div className="mt-1 text-sky-800 dark:text-sky-200">
            Camera app pushes here. OBS pulls the same URL once.
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200">
          No local relay
        </span>
      </div>

      <label className="mt-2 block">
        <span className="mb-1 block text-[10px] font-semibold uppercase tracking-normal text-sky-700 dark:text-sky-200">
          Public relay origin
        </span>
        <input
          value={origin}
          onChange={(event) => setOrigin(event.target.value)}
          className="w-full rounded border border-sky-200 bg-white px-2 py-1 text-[11px] text-gray-900 dark:border-sky-900 dark:bg-gray-950 dark:text-gray-100"
          data-testid="public-rtmp-origin-input"
        />
      </label>

      <div className="mt-2 grid gap-2">
        <CopyField label="RTMP URL for camera app and OBS" value={publicRtmpUrl} onCopy={onCopy} />
      </div>

      <ol className="mt-2 space-y-1">
        <li>1. Paste this URL into the camera livestream/custom RTMP field.</li>
        <li>2. In OBS, add Media Source with the same URL, then start OBS Virtual Camera.</li>
        <li>3. Open computer source and choose OBS Virtual Camera in the browser device list.</li>
      </ol>

      <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
        YogaCoach reads OBS Virtual Camera, not this RTMP URL.
      </div>
    </div>
  );
}

export default PublicRtmpIngestPanel;
