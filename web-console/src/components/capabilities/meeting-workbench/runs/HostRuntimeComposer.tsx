import { useMemo, useState } from 'react';
import { Send, Square } from 'lucide-react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import { useT } from '@/lib/i18n';
import { useWorkspaceInteractionTargetRegistration } from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import {
  workspaceInteractionRevision,
  type WorkspaceInteractionTarget,
} from '@/lib/workspace-interaction/workspaceInteractionTarget';
import { transcribeWorkspaceAudio } from '@/lib/workspace-interaction/workspaceSpeechToTextClient';
import type { HostRuntimeGraphContext } from './hostRuntimeGraphContext';

export function HostRuntimeComposer({
  apiUrl,
  workspaceId,
  meetingId,
  sessionId,
  selectedObjectRef,
  graphContext,
  disabled,
  onSubmit,
}: {
  apiUrl: string;
  workspaceId?: string;
  meetingId?: string | null;
  sessionId?: string | null;
  selectedObjectRef?: AddressableObjectRef | null;
  graphContext?: HostRuntimeGraphContext | null;
  disabled: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const t = useT();
  const [prompt, setPrompt] = useState('');
  const [pinnedPrompt, setPinnedPrompt] = useState('');

  function handleAppendTranscript(transcript: string) {
    setPrompt((current) => {
      const prefix = current.trim().length > 0 ? `${current.trimEnd()} ` : '';
      return `${prefix}${transcript}`.trim();
    });
  }

  const interactionTarget = useMemo<WorkspaceInteractionTarget | null>(() => {
    if (!workspaceId || disabled) {
      return null;
    }
    return {
      targetId: `host_runtime_prompt:${workspaceId}:${sessionId || 'unbound'}`,
      targetKind: 'host_runtime_prompt',
      targetLabel: t('workspaceVoiceTargetHostRuntime' as any),
      revision: workspaceInteractionRevision('host_runtime_prompt', {
        workspace_id: workspaceId,
        meeting_id: meetingId || null,
        session_id: sessionId || null,
        selected_object_ref: selectedObjectRef || null,
        graph_context: graphContext || null,
        draft: prompt,
      }),
      submissionPolicy: 'review_then_submit',
      freezeContext: () => ({
        workspace_id: workspaceId,
        meeting_id: meetingId || null,
        session_id: sessionId || null,
        selected_object_ref: selectedObjectRef || null,
        graph_context: graphContext || null,
        draft: prompt,
      }),
      submitVoiceTurn: async (turn) => {
        const response = await transcribeWorkspaceAudio({
          apiUrl,
          audioBase64: turn.audioBase64,
          language: turn.language,
        });
        const transcript = response.text.trim();
        if (!transcript) {
          return {
            status: 'ignored_empty_transcript',
            transcript: '',
          };
        }
        handleAppendTranscript(transcript);
        return {
          status: 'draft_updated',
          transcript,
        };
      },
    };
  }, [
    apiUrl,
    disabled,
    graphContext,
    meetingId,
    prompt,
    selectedObjectRef,
    sessionId,
    t,
    workspaceId,
  ]);
  const activateInteractionTarget =
    useWorkspaceInteractionTargetRegistration(interactionTarget);

  return (
    <form
      className="flex h-full min-h-0 flex-col gap-3"
      data-testid="host-runtime-composer"
      onSubmit={(event) => {
        event.preventDefault();
        const value = prompt.trim();
        if (!value || disabled) return;
        setPinnedPrompt(value);
        onSubmit(value);
        setPrompt('');
      }}
    >
      {pinnedPrompt ? (
        <div
          className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200"
          data-testid="host-runtime-pinned-prompt"
        >
          <div className="font-semibold uppercase tracking-[0.08em]">Pinned instruction</div>
          <div className="mt-1 whitespace-pre-wrap text-sm leading-5">{pinnedPrompt}</div>
        </div>
      ) : null}
      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        onFocus={activateInteractionTarget}
        onPointerDown={activateInteractionTarget}
        className="min-h-0 flex-1 resize-none rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
        placeholder="Ask the host runtime agent to operate on this meeting context..."
        data-testid="host-runtime-prompt"
        data-workspace-interaction-target="host_runtime_prompt"
        disabled={disabled}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] text-slate-500 dark:text-slate-400">
          {t('workspaceVoicePolicyReview' as any)}
        </span>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 px-2 text-xs font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300"
            disabled
          >
            <Square className="h-3.5 w-3.5" aria-hidden="true" />
            Interrupt
          </button>
          <button
            type="submit"
            className="inline-flex h-8 items-center gap-1 rounded-md bg-blue-600 px-3 text-xs font-semibold text-white disabled:bg-slate-300"
            disabled={disabled || !prompt.trim()}
            data-testid="host-runtime-submit"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            Run
          </button>
        </div>
      </div>
    </form>
  );
}
