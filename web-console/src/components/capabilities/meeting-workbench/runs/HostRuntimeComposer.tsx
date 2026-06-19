import { useState } from 'react';
import { Send, Square } from 'lucide-react';

import { HostRuntimeVoicePromptButton } from './HostRuntimeVoicePromptButton';

export function HostRuntimeComposer({
  apiUrl,
  disabled,
  onSubmit,
}: {
  apiUrl: string;
  disabled: boolean;
  onSubmit: (prompt: string) => void;
}) {
  const [prompt, setPrompt] = useState('');
  const [pinnedPrompt, setPinnedPrompt] = useState('');

  function handleAppendTranscript(transcript: string) {
    setPrompt((current) => {
      const prefix = current.trim().length > 0 ? `${current.trimEnd()} ` : '';
      return `${prefix}${transcript}`.trim();
    });
  }

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
        className="min-h-0 flex-1 resize-none rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
        placeholder="Ask the host runtime agent to operate on this meeting context..."
        data-testid="host-runtime-prompt"
        disabled={disabled}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <HostRuntimeVoicePromptButton
          apiUrl={apiUrl}
          disabled={disabled}
          onTranscript={handleAppendTranscript}
        />
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
