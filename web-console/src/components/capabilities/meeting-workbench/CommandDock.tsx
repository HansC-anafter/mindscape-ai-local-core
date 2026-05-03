import React, { useMemo } from 'react';
import { MessageSquare, Send } from 'lucide-react';

import { applyMentionToken, getMentionQuery } from './meetingMentions';
import type { MeetingMentionItem, MeetingPackTool, MeetingTranslate } from './meetingWorkbenchTypes';

export function MeetingCommandBar({
  command,
  onCommandChange,
  onSubmitCommand,
  isDispatching,
  isConsoleOpen,
  onToggleConsole,
  packTools,
  selectedPackToolId,
  onSelectedPackToolChange,
  packToolsLoading,
  packToolsError,
  hasActiveMeeting,
  mentionItems,
  mentionItemsLoading,
  mentionItemsError,
  onApplyMention,
  missingContextLabel,
  t,
}: {
  command: string;
  onCommandChange: (value: string) => void;
  onSubmitCommand: () => void | Promise<void>;
  isDispatching: boolean;
  isConsoleOpen: boolean;
  onToggleConsole: () => void;
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  onSelectedPackToolChange: (toolId: string) => void;
  packToolsLoading: boolean;
  packToolsError: string | null;
  hasActiveMeeting: boolean;
  mentionItems: MeetingMentionItem[];
  mentionItemsLoading: boolean;
  mentionItemsError: string | null;
  onApplyMention: (item: MeetingMentionItem) => void;
  missingContextLabel: string | null;
  t: MeetingTranslate;
}) {
  const selectedPackTool = packTools.find((tool) => tool.id === selectedPackToolId) ?? null;
  const mentionQuery = getMentionQuery(command);
  const mentionOptions = useMemo(() => {
    if (mentionQuery === null) {
      return [];
    }

    return mentionItems
      .filter((item) => {
        const haystack = `${item.label} ${item.token} ${item.description} ${item.kind} ${
          item.searchText || ''
        }`.toLowerCase();
        return haystack.includes(mentionQuery);
      })
      .slice(0, 8);
  }, [mentionItems, mentionQuery]);
  const showMentionPicker = hasActiveMeeting && mentionQuery !== null;
  const showMissingContext = hasActiveMeeting && Boolean(missingContextLabel);

  const applyMention = (item: MeetingMentionItem) => {
    onCommandChange(applyMentionToken(command, item.token));
    onApplyMention(item);
    if (item.packToolId) {
      onSelectedPackToolChange(item.packToolId);
    }
  };

  return (
    <form
      className="flex shrink-0 items-center gap-2 border-t border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-command-bar"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmitCommand();
      }}
    >
      <button
        type="button"
        onClick={onToggleConsole}
        className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors ${
          isConsoleOpen
            ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
            : 'border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900'
        }`}
        aria-label={isConsoleOpen ? t('meetingWorkbenchCollapseConsole') : t('meetingWorkbenchOpenConsole')}
        data-testid="meeting-console-toggle"
      >
        <MessageSquare className="h-4 w-4" aria-hidden="true" />
      </button>
      <div className="hidden shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 md:block">
        {t('meetingWorkbenchPackTools')}
      </div>
      <select
        value={selectedPackToolId}
        disabled={isDispatching || !hasActiveMeeting}
        onChange={(event) => onSelectedPackToolChange(event.target.value)}
        className="h-9 w-44 shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 text-xs font-medium text-slate-700 outline-none transition-colors focus:border-blue-400 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-500"
        aria-label={t('meetingWorkbenchPackToolSelect')}
        data-testid="meeting-pack-tool-select"
        title={packToolsError || selectedPackTool?.description || t('meetingWorkbenchAutoRouteDescription')}
      >
        <option value="auto">{packToolsLoading ? t('meetingWorkbenchLoadingTools') : t('meetingWorkbenchAutoRoute')}</option>
        {packTools.map((tool) => (
          <option key={tool.id} value={tool.id}>
            {tool.capabilityCode ? `${tool.capabilityCode} / ${tool.label}` : tool.label}
          </option>
        ))}
      </select>
      <div className="relative min-w-0 flex-1">
        <input
          value={command}
          disabled={isDispatching || !hasActiveMeeting}
          onChange={(event) => onCommandChange(event.target.value)}
          className="h-9 w-full rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-400 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-blue-500"
          placeholder={
            isDispatching
              ? t('meetingWorkbenchDispatching')
              : !hasActiveMeeting
                ? t('meetingWorkbenchSelectMeetingFirst')
                : selectedPackTool
                  ? t('meetingWorkbenchAskPackToolPlaceholder', { value: selectedPackTool.label })
                  : t('meetingWorkbenchCommandPlaceholder')
          }
          aria-label={t('meetingWorkbenchCommandInputLabel')}
          aria-describedby={showMissingContext ? 'meeting-command-missing-context' : undefined}
          aria-autocomplete="list"
          aria-expanded={showMentionPicker}
        />
        {showMissingContext && missingContextLabel ? (
          <div
            id="meeting-command-missing-context"
            className="mt-1 flex min-w-0 items-center gap-2 text-[11px]"
            data-testid="meeting-command-missing-context"
          >
            <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
              {t('meetingWorkbenchCommandMissingContext', { value: missingContextLabel })}
            </span>
            <span className="truncate text-slate-500 dark:text-slate-400">
              {t('meetingWorkbenchCommandMissingContextDetail')}
            </span>
          </div>
        ) : null}
        {showMentionPicker ? (
          <div
            className="absolute bottom-full left-0 z-40 mb-2 w-[min(34rem,calc(100vw-8rem))] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
            data-testid="meeting-mention-picker"
            role="listbox"
            aria-label="Meeting references"
          >
            <div className="border-b border-slate-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
              {t('meetingWorkbenchInsertReference')}
            </div>
            {mentionOptions.length > 0 ? (
              <div className="max-h-64 overflow-auto py-1">
                {mentionOptions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      applyMention(item);
                    }}
                    className="flex w-full items-start gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-slate-100 dark:hover:bg-slate-900"
                    role="option"
                    data-testid={`meeting-mention-option-${item.id}`}
                  >
                    <span className="mt-0.5 shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                      {item.kind}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-slate-900 dark:text-slate-100">
                        {item.label}
                      </span>
                      <span className="block truncate text-slate-500 dark:text-slate-400">
                        {item.description}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-blue-600 dark:text-blue-300">
                      {item.token}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                {mentionItemsLoading
                  ? t('meetingWorkbenchLoadingReferences')
                  : mentionItemsError
                    ? t('meetingWorkbenchReferenceSearchUnavailable', { value: mentionItemsError })
                    : t('meetingWorkbenchNoMatchingReference')}
              </div>
            )}
          </div>
        ) : null}
      </div>
      <button
        type="submit"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-900 text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
        aria-label={t('meetingWorkbenchSendInstruction')}
        data-testid="meeting-command-submit"
        disabled={!hasActiveMeeting || !command.trim() || isDispatching}
      >
        <Send className="h-4 w-4" aria-hidden="true" />
      </button>
    </form>
  );
}
