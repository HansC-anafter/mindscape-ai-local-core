'use client';

import React from 'react';
import { Mic, Radio, Square, X } from 'lucide-react';

import { useT } from '@/lib/i18n';
import { useWorkspaceInteractionIngress } from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';

import {
  useWorkspaceVoiceInteractionController,
  type WorkspaceVoiceState,
} from './WorkspaceVoiceInteractionController';
import { useWorkspaceVoiceMeetingBootstrap } from './WorkspaceVoiceMeetingBootstrapProvider';

function stateMessageKey(state: WorkspaceVoiceState): string | null {
  if (state === 'requesting_permission') return 'workspaceVoiceStateRequestingPermission';
  if (state === 'recording' || state === 'realtime_listening') {
    return 'workspaceVoiceStateRecording';
  }
  if (state === 'transcribing') return 'workspaceVoiceStateTranscribing';
  if (state === 'submitting' || state === 'realtime_connecting') {
    return 'workspaceVoiceStateSubmitting';
  }
  if (state === 'draft_updated') return 'workspaceVoiceStateDraftUpdated';
  if (state === 'submitted') return 'workspaceVoiceStateSubmitted';
  if (state === 'answered' || state === 'realtime_answered') {
    return 'workspaceVoiceStateAnswered';
  }
  if (
    state === 'semantic_clarification'
    || state === 'realtime_clarification'
  ) {
    return 'workspaceVoiceStateClarification';
  }
  if (state === 'permission_denied') return 'workspaceVoiceStatePermissionDenied';
  if (state === 'unavailable') return 'workspaceVoiceStateUnavailable';
  if (state === 'empty') return 'workspaceVoiceStateEmpty';
  if (state === 'stale_target') return 'workspaceVoiceStateStaleTarget';
  if (state === 'realtime_interrupted') return 'workspaceVoiceStateInterrupted';
  if (state === 'realtime_speech_unavailable') {
    return 'workspaceVoiceStateSpeechUnavailable';
  }
  if (state === 'error') return 'workspaceVoiceStateError';
  return null;
}

export function WorkspaceVoiceInteractionPanel({
  apiUrl,
}: {
  apiUrl: string;
}) {
  const t = useT();
  const ingress = useWorkspaceInteractionIngress();
  const bootstrap = useWorkspaceVoiceMeetingBootstrap();
  const controller = useWorkspaceVoiceInteractionController(apiUrl);
  React.useEffect(() => {
    if (
      ingress.targets.length === 0
      && bootstrap.status === 'idle'
    ) {
      void bootstrap.ensureMeetingTarget().catch(() => undefined);
    }
  }, [bootstrap, ingress.targets.length]);
  const realtimeActive = [
    'realtime_connecting',
    'realtime_listening',
    'transcribing',
    'realtime_interrupted',
    'realtime_speech_unavailable',
    'realtime_answered',
    'realtime_clarification',
  ].includes(controller.state) && controller.mode === 'realtime';
  const boundedRecording = controller.state === 'recording'
    && controller.mode === 'bounded';
  const busy = [
    'requesting_permission',
    'transcribing',
    'submitting',
    'realtime_connecting',
  ].includes(controller.state) || controller.turnInFlight;
  const statusKey = stateMessageKey(controller.state);

  return (
    <section
      className="flex min-h-full flex-col gap-4 p-4"
      data-testid="workspace-voice-panel"
      data-state={controller.state}
    >
      <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
        {t('workspaceVoicePanelDescription' as any)}
      </p>

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
          {t('workspaceVoiceTargetLabel' as any)}
        </div>
        {controller.activeTarget ? (
          <>
            <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
              {controller.activeTarget.targetLabel}
            </div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {controller.activeTarget.submissionPolicy === 'direct_submit'
                ? t('workspaceVoicePolicyDirect' as any)
                : t('workspaceVoicePolicyReview' as any)}
            </div>
          </>
        ) : bootstrap.status === 'starting' || bootstrap.status === 'idle' ? (
          <div
            className="mt-1 text-xs text-blue-700 dark:text-blue-300"
            role="status"
            data-testid="workspace-voice-meeting-bootstrap-starting"
          >
            {t('workspaceVoiceMeetingBootstrapStarting' as any)}
          </div>
        ) : bootstrap.status === 'failed' ? (
          <div
            className="mt-1 text-xs text-rose-700 dark:text-rose-300"
            role="alert"
            data-testid="workspace-voice-meeting-bootstrap-failed"
          >
            <div>{t('workspaceVoiceMeetingBootstrapFailed' as any)}</div>
            <button
              type="button"
              className="mt-2 rounded-md border border-rose-300 px-2 py-1 font-semibold dark:border-rose-800"
              onClick={() => {
                void bootstrap.ensureMeetingTarget().catch(() => undefined);
              }}
              data-testid="workspace-voice-meeting-bootstrap-retry"
            >
              {t('workspaceVoiceMeetingBootstrapRetry' as any)}
            </button>
          </div>
        ) : (
          <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">
            {t('workspaceVoiceNoTarget' as any)}
          </div>
        )}
      </div>

      <div
        className="grid grid-cols-2 gap-2"
        role="group"
        aria-label={t('workspaceVoiceModeGroupLabel' as any)}
      >
        <button
          type="button"
          className={`rounded-md border px-3 py-2 text-xs font-semibold ${
            controller.mode === 'bounded'
              ? 'border-blue-400 bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-200'
              : 'border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-300'
          }`}
          onClick={() => controller.setMode('bounded')}
          disabled={busy}
          data-testid="workspace-voice-mode-bounded"
        >
          {t('workspaceVoiceModeBounded' as any)}
        </button>
        <button
          type="button"
          className={`rounded-md border px-3 py-2 text-xs font-semibold ${
            controller.mode === 'realtime'
              ? 'border-emerald-400 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-200'
              : 'border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-300'
          } disabled:cursor-not-allowed disabled:opacity-50`}
          onClick={() => controller.setMode('realtime')}
          disabled={!controller.realtimeAvailable || busy}
          title={!controller.realtimeAvailable
            ? t('workspaceVoiceRealtimeUnavailable' as any)
            : undefined}
          data-testid="workspace-voice-mode-realtime"
        >
          {t('workspaceVoiceModeRealtime' as any)}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className={`inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold text-white ${
            boundedRecording
              ? 'bg-red-600 hover:bg-red-700'
              : realtimeActive
                ? 'bg-emerald-600 hover:bg-emerald-700'
                : 'bg-blue-600 hover:bg-blue-700'
          } disabled:cursor-not-allowed disabled:bg-slate-300`}
          onClick={() => {
            if (boundedRecording || realtimeActive) {
              void controller.stop();
            } else {
              void controller.start();
            }
          }}
          disabled={
            !controller.activeTarget
            || busy
            || bootstrap.status === 'starting'
          }
          data-testid="workspace-voice-primary-control"
        >
          {boundedRecording || realtimeActive ? (
            <Square className="h-4 w-4" aria-hidden="true" />
          ) : controller.mode === 'realtime' ? (
            <Radio className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Mic className="h-4 w-4" aria-hidden="true" />
          )}
          {boundedRecording || realtimeActive
            ? t('workspaceVoiceStop' as any)
            : t('workspaceVoiceStart' as any)}
        </button>
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900"
          onClick={controller.cancel}
          disabled={busy}
          aria-label={t('workspaceVoiceCancel' as any)}
          title={t('workspaceVoiceCancel' as any)}
          data-testid="workspace-voice-cancel"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {controller.mode === 'realtime' && realtimeActive ? (
        <button
          type="button"
          className="rounded-md border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 dark:border-slate-800 dark:text-slate-300"
          onClick={controller.interruptRealtime}
          data-testid="workspace-voice-realtime-interrupt"
        >
          {t('workspaceVoiceInterrupt' as any)}
        </button>
      ) : null}

      {statusKey ? (
        <div
          className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-700 dark:bg-slate-900 dark:text-slate-200"
          role="status"
        >
          {t(statusKey as any)}
        </div>
      ) : null}
      {controller.transcript ? (
        <div className="rounded-md border border-slate-200 p-3 text-sm text-slate-800 dark:border-slate-800 dark:text-slate-100">
          {controller.transcript}
        </div>
      ) : null}
      {controller.answerText ? (
        <div
          className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100"
          data-testid="workspace-voice-answer"
        >
          {controller.answerText}
        </div>
      ) : null}
      {controller.error ? (
        <div className="text-xs text-rose-700 dark:text-rose-300">
          {controller.error}
        </div>
      ) : null}
    </section>
  );
}
