import React, { useMemo, useState } from "react";
import { FileText, PlusCircle, X } from "lucide-react";

import { formatKind } from "./meetingGraphProjection";
import { getSessionDisplayTitle, getSessionSearchCorpus } from "./meetingSessionContext";
import type { AOLMeetingBottomShellProps, MeetingSessionSummary } from "./meetingWorkbenchTypes";
import { shortId } from "./meetingWorkbenchUtils";
function formatSessionTime(value: string | undefined): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('sv-SE', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).replace(',', '');
}
export function MeetingSessionStrip({
  sessions,
  activeMeetingId,
  loading,
  error,
  onSelectSession,
}: {
  sessions: MeetingSessionSummary[];
  activeMeetingId: string;
  loading: boolean;
  error: string | null;
  onSelectSession: (session: MeetingSessionSummary) => void;
}) {
  if (loading && sessions.length === 0) {
    return (
      <div
        className="flex h-10 items-center rounded-md border border-slate-200 bg-white/90 px-3 text-xs text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-950/90 dark:text-slate-400"
        data-testid="meeting-session-strip"
      >
        Loading meeting sessions...
      </div>
    );
  }

  if (sessions.length === 0) {
    return error ? (
      <div
        className="flex h-10 items-center rounded-md border border-amber-200 bg-amber-50/95 px-3 text-xs text-amber-700 shadow-sm dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300"
        data-testid="meeting-session-strip"
      >
        {error}
      </div>
    ) : null;
  }

  return (
    <div
      className="flex max-w-full items-center gap-2 overflow-x-auto rounded-md border border-slate-200 bg-white/95 px-2 py-1.5 shadow-sm dark:border-slate-800 dark:bg-slate-950/95"
      data-testid="meeting-session-strip"
      aria-label="Meeting sessions"
    >
      <div className="shrink-0 px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
        Sessions
      </div>
      {sessions.map((session) => {
        const isActive = session.id === activeMeetingId;
        return (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelectSession(session)}
            className={`grid min-w-[150px] max-w-[190px] shrink-0 gap-0.5 rounded-md border px-2 py-1.5 text-left transition-colors ${
              isActive
                ? 'border-blue-400 bg-blue-50 text-blue-950 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-100'
                : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
            }`}
            aria-pressed={isActive}
            title={session.id}
            data-testid={`meeting-session-card-${session.id}`}
          >
            <span className="truncate text-[11px] font-semibold">{getSessionDisplayTitle(session)}</span>
            <span className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.08em] opacity-70">
              <span className="truncate">{session.status || 'session'}</span>
              <span className="shrink-0">{formatSessionTime(session.started_at)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function MeetingObjectContextPanel({
  summary,
  selection,
  attachResponse,
  meetingId,
  surfaceRoute,
  onSwitchObject,
  onClose,
  presentation = 'floating',
}: Pick<
  AOLMeetingBottomShellProps,
  'summary' | 'selection' | 'attachResponse' | 'meetingId' | 'surfaceRoute' | 'onSwitchObject'
> & {
  onClose: () => void;
  presentation?: 'floating' | 'drawer';
}) {
  const ref = summary?.ref ?? null;
  const labels = summary?.labels ?? [];
  const ownerSurfaceUrl = summary?.owner_surface_url || surfaceRoute;
  const sourceSurface = ref?.source_surface || selection?.sourceSurface || 'current surface';
  const hasObjectContext = Boolean(summary || selection || attachResponse);

  return (
    <section
      className={presentation === 'drawer'
        ? 'flex h-full min-h-0 w-full flex-col overflow-hidden bg-white dark:bg-slate-950'
        : 'pointer-events-auto flex max-h-full w-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950'}
      id="meeting-object-context-panel"
      data-testid="meeting-object-context-panel"
      aria-label="Meeting object context"
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Object Context
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Close object context"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="mt-1 truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
              {summary?.title || selection?.label || 'Meeting sessions'}
            </h2>
          </div>
          <div className="shrink-0 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold uppercase text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
            {hasObjectContext ? 'Attached' : 'Browser'}
          </div>
        </div>

        <dl className="mt-3 grid gap-2 text-xs">
          <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Meeting
            </dt>
            <dd className="mt-1 truncate font-mono text-slate-800 dark:text-slate-100">{shortId(meetingId)}</dd>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
              <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Owner
              </dt>
              <dd className="mt-1 truncate font-medium text-slate-800 dark:text-slate-100">
                {ref?.owner_pack || selection?.ownerPack || 'unknown'}
              </dd>
            </div>
            <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
              <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Kind
              </dt>
              <dd className="mt-1 truncate font-medium text-slate-800 dark:text-slate-100">
                {formatKind(ref?.object_kind || selection?.objectKind)}
              </dd>
            </div>
          </div>
          <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Source
            </dt>
            <dd className="mt-1 truncate text-slate-800 dark:text-slate-100">{sourceSurface}</dd>
          </div>
        </dl>

        <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Object labels">
          {labels.slice(0, 5).map((label) => (
            <span
              key={label}
              className="max-w-full truncate rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {label}
            </span>
          ))}
          {labels.length === 0 ? (
            <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              No labels
            </span>
          ) : null}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md border border-slate-200 px-2.5 py-2 dark:border-slate-800">
            <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Attachments
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
              {attachResponse?.attachments.length ?? 0}
            </div>
          </div>
          <div className="rounded-md border border-slate-200 px-2.5 py-2 dark:border-slate-800">
            <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Review
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
              {attachResponse?.review_routes.length ?? 0}
            </div>
          </div>
        </div>
      </div>

      <div className="grid shrink-0 gap-2 border-t border-slate-200 p-3 dark:border-slate-800">
        <a
          href={ownerSurfaceUrl}
          className="rounded-md border border-slate-300 px-3 py-2 text-center text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900"
        >
          Open Owner Surface
        </a>
        <button
          type="button"
          onClick={() => {
            onSwitchObject();
            onClose();
          }}
          className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 transition-colors hover:bg-blue-100 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300 dark:hover:bg-blue-950/60"
        >
          Switch Object
        </button>
      </div>
    </section>
  );
}

export function MeetingSessionsPopover({
  sessions,
  activeMeetingId,
  loading,
  error,
  creating,
  createError,
  onCreateSession,
  onSelectSession,
  onClose,
  presentation = 'floating',
}: {
  sessions: MeetingSessionSummary[];
  activeMeetingId: string;
  loading: boolean;
  error: string | null;
  creating: boolean;
  createError: string | null;
  onCreateSession: () => void;
  onSelectSession: (session: MeetingSessionSummary) => void;
  onClose: () => void;
  presentation?: 'floating' | 'drawer';
}) {
  const [sessionQuery, setSessionQuery] = useState('');
  const normalizedQuery = sessionQuery.trim().toLowerCase();
  const visibleSessions = useMemo(() => {
    if (!normalizedQuery) {
      return sessions.slice(0, 24);
    }

    return sessions.filter((session) => getSessionSearchCorpus(session).includes(normalizedQuery));
  }, [normalizedQuery, sessions]);
  const resultLabel = normalizedQuery
    ? `${visibleSessions.length}/${sessions.length}`
    : `${Math.min(visibleSessions.length, sessions.length)}/${sessions.length}`;

  return (
    <section
      className={presentation === 'drawer'
        ? 'flex h-full min-h-0 flex-col bg-white dark:bg-slate-950'
        : 'pointer-events-auto rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950'}
      id="meeting-sessions-popover"
      data-testid="meeting-sessions-popover"
      aria-label="Meeting sessions"
    >
      <div className="flex h-10 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Sessions
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            {sessions.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onCreateSession}
            disabled={creating}
            className="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2 text-[11px] font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 disabled:cursor-wait disabled:opacity-60 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-100"
            data-testid="meeting-session-create"
          >
            <PlusCircle className="h-3.5 w-3.5" aria-hidden="true" />
            {creating ? 'Creating' : 'New'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
            aria-label="Close meeting sessions"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="p-2">
        {createError ? (
          <div className="mb-2 rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300">
            {createError}
          </div>
        ) : null}
        <div className="mb-2 flex items-center gap-2">
          <input
            type="search"
            value={sessionQuery}
            onChange={(event) => setSessionQuery(event.target.value)}
            className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-blue-600 dark:focus:ring-blue-950"
            placeholder="Search session, object, agenda..."
            aria-label="Search meeting sessions"
            data-testid="meeting-session-search"
          />
          <span
            className="shrink-0 rounded bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-500 dark:bg-slate-900 dark:text-slate-400"
            data-testid="meeting-session-result-count"
          >
            {resultLabel}
          </span>
        </div>
        {visibleSessions.length > 0 || loading || error ? (
          <MeetingSessionStrip
            sessions={visibleSessions}
            activeMeetingId={activeMeetingId}
            loading={loading}
            error={error}
            onSelectSession={onSelectSession}
          />
        ) : (
          <div
            className="flex h-10 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"
            data-testid="meeting-session-empty"
          >
            No matching sessions.
          </div>
        )}
      </div>
    </section>
  );
}
