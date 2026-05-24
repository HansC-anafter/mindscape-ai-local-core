'use client';

import React, { useCallback } from 'react';
import { t } from '@/lib/i18n';
import IntentChips from '../../app/workspaces/components/IntentChips';
import { useUIState } from '@/contexts/UIStateContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { useMessages } from '@/contexts/MessagesContext';
import { WorkspaceChatRuntimeControls } from './WorkspaceChatRuntimeControls';
import { getApiBaseUrl } from '@/lib/api-url';

interface WorkspaceChatMeetingSidebarProps {
  workspaceId: string;
  apiUrl?: string;
}

export default function WorkspaceChatMeetingSidebar({
  workspaceId,
  apiUrl = '',
}: WorkspaceChatMeetingSidebarProps) {
  const { quickStartSuggestions } = useMessages();
  const { setInput } = useUIState();
  const { textareaRef } = useWorkspaceRefs();
  const resolvedApiUrl = apiUrl || getApiBaseUrl();

  const queueSuggestion = useCallback((suggestion: string) => {
    setInput(suggestion);
    window.setTimeout(() => {
      textareaRef.current?.focus();
    }, 100);
  }, [setInput, textareaRef]);

  return (
    <aside
      className="flex h-full w-[min(272px,25vw)] shrink-0 flex-col border-l border-[#dcc9a5] bg-[linear-gradient(180deg,#f7f0df_0%,#f6edd8_52%,#f2e6cd_100%)] dark:border-slate-800 dark:bg-slate-950"
      data-testid="workspace-chat-meeting-sidebar"
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <section className="sticky top-0 z-10 rounded-[18px] border border-[#d9c39c] bg-white/90 p-3 shadow-[0_10px_24px_rgba(166,139,94,0.10)] backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#8b6c33] dark:text-slate-400">
            Runtime
          </div>
          <div className="mt-2">
            <WorkspaceChatRuntimeControls
              workspaceId={workspaceId}
              apiUrl={resolvedApiUrl}
              layout="panel"
            />
          </div>
        </section>

        {quickStartSuggestions.length > 0 ? (
          <section className="mt-3 rounded-[18px] border border-[#d9c39c] bg-white/75 p-3 shadow-[0_10px_24px_rgba(166,139,94,0.08)] dark:border-slate-800 dark:bg-slate-900/80">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#8b6c33] dark:text-slate-400">
              Prompts
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {quickStartSuggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => queueSuggestion(suggestion)}
                  className="rounded-full border border-[#c7af7d] bg-white/95 px-2.5 py-1 text-[11px] font-medium leading-4 text-slate-700 transition-colors hover:bg-[#fff8ea] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {suggestion.startsWith('suggestion.') || suggestion.startsWith('suggestions.')
                    ? t(suggestion as any) || suggestion
                    : suggestion}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <section className="mt-3 rounded-[18px] border border-[#d9c39c] bg-white/75 p-3 shadow-[0_10px_24px_rgba(166,139,94,0.08)] dark:border-slate-800 dark:bg-slate-900/80">
          <IntentChips
            workspaceId={workspaceId}
            apiUrl={resolvedApiUrl}
            compact
          />
        </section>
      </div>
    </aside>
  );
}
