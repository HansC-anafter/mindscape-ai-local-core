'use client';

import React from 'react';
import { Camera, Clipboard, ExternalLink, Loader2, MonitorUp, RadioTower } from 'lucide-react';

import {
  callCaptureRelayControl,
  type CaptureRelayAction,
  type CaptureRelayResponse,
} from './captureRelayClient';

interface CaptureRelayLauncherCardProps {
  apiBase: string;
  desktopDeviceLink: string;
  disabled?: boolean;
  pairingCode?: string;
}

function statusLabel(result: CaptureRelayResponse | null): string {
  if (!result) {
    return 'Not checked';
  }
  if (result.status === 'running') {
    return result.relay?.mode === 'managed' ? 'Relay running' : 'External relay detected';
  }
  if (result.status === 'ready_to_start') {
    return 'Ready to start';
  }
  if (result.reason === 'relay_binary_missing') {
    return 'Relay binary missing';
  }
  return result.status || result.reason || 'Unknown';
}

function statusClassName(result: CaptureRelayResponse | null): string {
  if (result?.status === 'running') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200';
  }
  if (result?.status === 'ready_to_start') {
    return 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-200';
  }
  return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100';
}

function FieldRow({
  label,
  value,
  onCopy,
}: {
  label: string;
  value?: string;
  onCopy: (value: string) => void;
}) {
  return (
    <div className="rounded border border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-950">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all text-[11px] text-gray-900 dark:text-gray-100">
          {value || 'Waiting for relay status'}
        </code>
        <button
          type="button"
          disabled={!value}
          onClick={() => value && onCopy(value)}
          className="shrink-0 rounded border border-gray-300 p-1 text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-300 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label={`Copy ${label}`}
        >
          <Clipboard className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export function CaptureRelayLauncherCard({
  apiBase,
  desktopDeviceLink,
  disabled = false,
  pairingCode,
}: CaptureRelayLauncherCardProps) {
  const [streamName, setStreamName] = React.useState('external-camera');
  const [pendingAction, setPendingAction] = React.useState<CaptureRelayAction | null>(null);
  const [result, setResult] = React.useState<CaptureRelayResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [copyState, setCopyState] = React.useState<'idle' | 'copied' | 'failed'>('idle');

  async function runAction(action: CaptureRelayAction, openObs = false) {
    if (disabled) {
      return;
    }
    setPendingAction(action);
    setError(null);
    try {
      const nextResult = await callCaptureRelayControl({
        apiBase,
        request: {
          action,
          stream_name: streamName,
          open_obs: openObs,
          timeout_ms: 5000,
        },
      });
      setResult(nextResult);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function copyValue(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 1600);
    } catch {
      setCopyState('failed');
    }
  }

  const publishUrl = result?.urls?.publish_url;
  const readUrl = result?.urls?.read_url;
  const relayRunning = result?.relay?.running === true;
  const actionDisabled = disabled || pendingAction !== null;

  return (
    <div
      className="mt-2 rounded border border-gray-200 bg-gray-50 p-2 dark:border-gray-800 dark:bg-gray-900"
      data-testid="capture-relay-launcher-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1 font-semibold text-gray-900 dark:text-gray-100">
            <RadioTower className="h-3.5 w-3.5 text-sky-500" aria-hidden="true" />
            RTMP to OBS Virtual Camera
          </div>
          <div className="mt-1 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
            Start a neutral host relay, send the external camera app to RTMP, read it in OBS,
            then select OBS Virtual Camera in this computer source.
          </div>
        </div>
        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClassName(result)}`}>
          {statusLabel(result)}
        </span>
      </div>

      <label className="mt-2 block">
        <span className="mb-1 block text-[10px] font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Stream path
        </span>
        <input
          value={streamName}
          onChange={(event) => setStreamName(event.target.value)}
          className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-900 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
          data-testid="capture-relay-stream-name-input"
        />
      </label>

      <div className="mt-2 grid gap-2">
        <FieldRow label="External camera RTMP URL" value={publishUrl} onCopy={copyValue} />
        <FieldRow label="OBS Media Source URL" value={readUrl} onCopy={copyValue} />
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => void runAction('status')}
          disabled={actionDisabled}
          className="inline-flex items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
        >
          {pendingAction === 'status' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
          Check relay
        </button>
        <button
          type="button"
          onClick={() => void runAction('start')}
          disabled={actionDisabled}
          className="inline-flex items-center justify-center gap-1 rounded bg-sky-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-gray-300 dark:disabled:bg-gray-800"
        >
          {pendingAction === 'start' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
          Start RTMP relay
        </button>
        <button
          type="button"
          onClick={() => void runAction('open_obs')}
          disabled={actionDisabled}
          className="inline-flex items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
        >
          <MonitorUp className="h-3.5 w-3.5" aria-hidden="true" />
          Open OBS
        </button>
        <button
          type="button"
          onClick={() => void runAction('stop')}
          disabled={actionDisabled || !relayRunning}
          className="inline-flex items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
        >
          Stop managed relay
        </button>
      </div>

      <ol className="mt-2 space-y-1 text-[11px] leading-4 text-gray-600 dark:text-gray-300">
        <li>1. Click Start RTMP relay; if blocked, install or expose the relay binary on host.</li>
        <li>2. Put the RTMP URL into the external camera app streaming field.</li>
        <li>3. In OBS, add Media Source and paste the OBS Media Source URL.</li>
        <li>4. Start OBS Virtual Camera, then open the computer source link and select it.</li>
      </ol>

      <a
        href={desktopDeviceLink}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex min-h-8 w-full items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-800 hover:bg-white dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
        aria-label="Open OBS Virtual Camera source"
      >
        <Camera className="h-3.5 w-3.5" aria-hidden="true" />
        Open computer source and select OBS Virtual Camera
        <ExternalLink className="h-3 w-3" aria-hidden="true" />
      </a>

      <div className="mt-2 rounded border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
        Pairing code: <span className="font-mono text-gray-900 dark:text-gray-100">{pairingCode || 'creating...'}</span>.
        Do not paste this code into a camera or gimbal.
      </div>

      {error ? (
        <div className="mt-2 rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] font-semibold text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      ) : null}
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
  );
}

export default CaptureRelayLauncherCard;
