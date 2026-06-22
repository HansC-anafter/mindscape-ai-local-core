'use client';

import React from 'react';
import { Camera, Clipboard, ExternalLink, Loader2, MonitorUp, RadioTower } from 'lucide-react';

import {
  callCaptureRelayControl,
  type CaptureRelayAction,
  type CaptureRelayResponse,
} from './captureRelayClient';
import { PublicRtmpIngestPanel } from './PublicRtmpIngestPanel';

interface CaptureRelayLauncherCardProps {
  apiBase: string;
  desktopDeviceLink: string;
  disabled?: boolean;
  pairingCode?: string;
}

const DEFAULT_RELEASE_URL = 'https://github.com/bluenviron/mediamtx/releases/latest';

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

function ReadinessPill({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div className="rounded border border-gray-200 bg-white px-2 py-1 dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <span className={ok ? 'text-[10px] font-semibold text-emerald-700 dark:text-emerald-200' : 'text-[10px] font-semibold text-amber-700 dark:text-amber-200'}>
          {ok ? 'Ready' : 'Blocked'}
        </span>
      </div>
      <div className="mt-0.5 break-all text-[11px] leading-4 text-gray-600 dark:text-gray-300">
        {detail}
      </div>
    </div>
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function inferPublisherReadiness(result: CaptureRelayResponse): {
  ok: boolean;
  detail: string;
} {
  const relayReady = result.relay?.running === true;
  const streamName = result.stream?.stream_name || result.urls?.stream_name || 'external-camera';
  if (!relayReady) {
    return {
      ok: false,
      detail: 'Start the relay before checking the external camera publisher.',
    };
  }
  if (result.stream?.has_publisher === true) {
    return {
      ok: true,
      detail: result.stream?.detail || `External publisher is streaming to ${streamName}.`,
    };
  }

  const recentOutput = result.relay?.recent_output || [];
  const escapedStreamName = escapeRegExp(streamName);
  const publishingPattern = new RegExp(`publishing to path ['"]?${escapedStreamName}['"]?`, 'i');
  const missingPathPattern = new RegExp(`path ['"]?${escapedStreamName}['"]? is not configured`, 'i');
  if (recentOutput.some((line) => publishingPattern.test(line))) {
    return {
      ok: true,
      detail: `External publisher is streaming to ${streamName}.`,
    };
  }

  const baseDetail = result.stream?.detail
    || (recentOutput.some((line) => missingPathPattern.test(line))
      ? 'OBS requested the stream, but no external RTMP publisher is connected to this path.'
      : 'No external RTMP publisher has been detected yet.');
  return {
    ok: false,
    detail: `${baseDetail} Put the External camera RTMP URL into the camera livestream app, then start streaming.`,
  };
}

function HostReadinessBlock({ result }: { result: CaptureRelayResponse }) {
  const relayReady = result.relay?.running === true;
  const obsReady = result.obs?.app_present === true;
  const websocketReady = result.obs?.websocket_reachable === true;
  const obsPath = result.obs?.app_path || '/Applications/OBS.app';
  const publisherReadiness = inferPublisherReadiness(result);

  return (
    <div className="mt-2 grid gap-1.5" data-testid="capture-relay-host-readiness">
      <ReadinessPill
        label="Relay"
        ok={relayReady}
        detail={relayReady ? 'MediaMTX is listening for RTMP.' : 'Start local relay before pairing an external provider.'}
      />
      <ReadinessPill
        label="OBS app"
        ok={obsReady}
        detail={obsReady ? `Found ${obsPath}.` : `Install OBS at ${obsPath}; mounted DMG apps are not a stable provider backend.`}
      />
      <ReadinessPill
        label="OBS websocket"
        ok={websocketReady}
        detail={websocketReady ? 'OBS control port is reachable.' : 'Open OBS and enable its WebSocket server before automated source setup.'}
      />
      <ReadinessPill
        label="External publisher"
        ok={publisherReadiness.ok}
        detail={publisherReadiness.detail}
      />
    </div>
  );
}

function InstallGuidanceBlock({
  result,
  onCopy,
}: {
  result: CaptureRelayResponse;
  onCopy: (value: string) => void;
}) {
  if (result.reason !== 'relay_binary_missing') {
    return null;
  }

  const guidance = result.install_guidance;
  const releaseUrl = guidance?.official_release_url || DEFAULT_RELEASE_URL;
  const homebrewOption = guidance?.options?.find((option) => option.id === 'homebrew');
  const releaseOption = guidance?.options?.find((option) => option.id === 'official_release');
  const brewCommand = homebrewOption?.command || 'brew install mediamtx';
  const brewAvailable = guidance?.host_tools?.brew_available === true;

  return (
    <div
      className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] leading-4 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100"
      data-testid="capture-relay-install-guidance"
    >
      <div className="font-semibold">Install MediaMTX before starting this relay</div>
      <div className="mt-1">
        Install MediaMTX from this wizard, or install it manually and click Check local relay again.
      </div>
      <div className="mt-2 rounded border border-amber-200 bg-white p-2 dark:border-amber-900 dark:bg-gray-950">
        <div className="font-semibold">
          Option 1: Homebrew {brewAvailable ? 'detected' : 'not detected on this host'}
        </div>
        <div className="mt-1 flex items-start gap-2">
          <code className="min-w-0 flex-1 break-all">{brewCommand}</code>
          <button
            type="button"
            onClick={() => onCopy(brewCommand)}
            className="shrink-0 rounded border border-amber-300 px-1.5 py-0.5 font-semibold hover:bg-amber-100 dark:border-amber-800 dark:hover:bg-amber-950"
          >
            Copy
          </button>
        </div>
      </div>
      <div className="mt-2 rounded border border-amber-200 bg-white p-2 dark:border-amber-900 dark:bg-gray-950">
        <div className="font-semibold">Option 2: Official release archive</div>
        <a
          href={releaseUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-1 font-semibold text-sky-700 hover:underline dark:text-sky-200"
        >
          Open MediaMTX releases
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
        <div className="mt-1">
          Download asset pattern:{' '}
          <code>
            {releaseOption?.asset_pattern
              || guidance?.recommended_asset_pattern
              || 'mediamtx_*_darwin_arm64.tar.gz'}
          </code>
        </div>
        <div>
          Put executable at:{' '}
          <code>
            {releaseOption?.install_target
              || '/opt/homebrew/bin/mediamtx or /usr/local/bin/mediamtx'}
          </code>
        </div>
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
          scene_name: action === 'configure_obs' ? 'Mindscape External Camera' : undefined,
          source_name: action === 'configure_obs' ? 'Mindscape RTSP Source' : undefined,
          install_method: action === 'install_mediamtx' ? 'homebrew' : undefined,
          open_obs: openObs,
          start_virtual_camera: action === 'configure_obs' ? true : undefined,
          timeout_ms: action === 'install_mediamtx' ? 120000 : action === 'configure_obs' ? 12000 : 5000,
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
  const obsWebsocketReady = result?.obs?.websocket_reachable === true;
  const actionDisabled = disabled || pendingAction !== null;
  const installBlocked = !result || result.reason === 'relay_binary_missing' || result.install_guidance?.status === 'missing';
  const obsMissing = result?.obs?.app_present === false;
  const canConfigureObs = relayRunning && obsWebsocketReady;

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
            Use public RTMP push-stream first. Keep the local host relay helper as a fallback
            when the camera app cannot reach the public relay.
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

      <PublicRtmpIngestPanel streamName={streamName} onCopy={copyValue} />

      <details
        className="mt-2 rounded border border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-950"
        data-testid="local-rtmp-relay-fallback"
      >
        <summary className="cursor-pointer text-[11px] font-semibold text-gray-800 dark:text-gray-100">
          Local host relay fallback
        </summary>
        <div className="mt-2 text-[11px] leading-4 text-gray-500 dark:text-gray-400">
          Use this only when the camera app must push to this computer instead of the public RTMP relay.
          It can install/check/start a local MediaMTX relay through the existing host-services proxy.
        </div>
        <div className="mt-2 grid gap-2">
          <FieldRow label="Local camera RTMP URL" value={publishUrl} onCopy={copyValue} />
          <FieldRow label="Local OBS Media Source URL" value={readUrl} onCopy={copyValue} />
        </div>

        {result ? <HostReadinessBlock result={result} /> : null}
        {result?.configure_result ? (
          <div className="mt-2 rounded border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] leading-4 text-sky-900 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100">
            OBS setup: <span className="font-semibold">{result.configure_result}</span>
            {result.obs_setup?.virtual_camera?.active === false ? ' · Virtual Camera is not active.' : null}
          </div>
        ) : null}
        {result ? <InstallGuidanceBlock result={result} onCopy={copyValue} /> : null}

        <div className="mt-2 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => void runAction('install_mediamtx')}
            disabled={actionDisabled || !installBlocked}
            className="inline-flex items-center justify-center gap-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:border-gray-300 disabled:bg-gray-100 disabled:text-gray-400 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100 dark:hover:bg-amber-950 dark:disabled:border-gray-700 dark:disabled:bg-gray-900 dark:disabled:text-gray-500"
            data-testid="capture-relay-install-button"
          >
            {pendingAction === 'install_mediamtx' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            Install MediaMTX
          </button>
          <button
            type="button"
            onClick={() => void runAction('status')}
            disabled={actionDisabled}
            className="inline-flex items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
          >
            {pendingAction === 'status' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            Check local relay
          </button>
          <button
            type="button"
            onClick={() => void runAction('start')}
            disabled={actionDisabled}
            className="inline-flex items-center justify-center gap-1 rounded bg-sky-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-gray-300 dark:disabled:bg-gray-800"
          >
            {pendingAction === 'start' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            Start local relay
          </button>
          <button
            type="button"
            onClick={() => void runAction('open_obs')}
            disabled={actionDisabled || obsMissing}
            className="inline-flex items-center justify-center gap-1 rounded border border-gray-300 px-2 py-1 text-[11px] font-semibold text-gray-700 hover:bg-white disabled:cursor-not-allowed disabled:text-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-950"
          >
            <MonitorUp className="h-3.5 w-3.5" aria-hidden="true" />
            Open OBS
          </button>
          <button
            type="button"
            onClick={() => void runAction('configure_obs')}
            disabled={actionDisabled || !canConfigureObs}
            className="inline-flex items-center justify-center gap-1 rounded border border-sky-300 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-800 hover:bg-sky-100 disabled:cursor-not-allowed disabled:border-gray-300 disabled:bg-gray-100 disabled:text-gray-400 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100 dark:hover:bg-sky-950 dark:disabled:border-gray-700 dark:disabled:bg-gray-900 dark:disabled:text-gray-500"
            data-testid="capture-relay-configure-obs-button"
          >
            {pendingAction === 'configure_obs' ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
            Configure OBS source
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
      </details>

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
