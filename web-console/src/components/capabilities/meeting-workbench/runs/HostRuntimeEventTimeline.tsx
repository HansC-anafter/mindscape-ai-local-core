import { useEffect, useMemo, useRef } from 'react';

import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

import { HostRuntimeStatusBadge } from './HostRuntimeStatusBadge';

interface TimelineItem {
  key: string;
  title: string;
  badge: string;
  detail: string | null;
  eventType: string;
  rawEventType: string | null;
}

const EVENT_LABELS: Record<string, string> = {
  'session.created': 'Session created',
  'session.ready': 'Ready',
  'turn.started': 'Run started',
  'turn.completed': 'Run completed',
  'turn.failed': 'Run failed',
  'item.started': 'Tool started',
  'item.completed': 'Tool completed',
  'tool.call': 'Tool call',
  'tool.output.delta': 'Tool output',
  'tool.output': 'Tool output',
  'runtime.progress': 'Runtime progress',
  'approval.requested': 'Approval requested',
  'governance.snapshot.recorded': 'Governance snapshot',
};

function humanizeEventType(eventType: string): string {
  return EVENT_LABELS[eventType] || eventType
    .split('.')
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}

function compactPayloadValue(value: unknown): string | null {
  if (typeof value === 'string') {
    return value.trim() || null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return null;
}

function payloadText(payload: Record<string, unknown>, key: string): string | null {
  return compactPayloadValue(payload[key]);
}

function eventTitle(event: HostRuntimeEvent): string {
  const payload = event.payload || {};
  return payloadText(payload, 'title') || humanizeEventType(event.event_type);
}

function eventDetail(event: HostRuntimeEvent): string | null {
  const payload = event.payload || {};
  return (
    compactPayloadValue(payload.detail) ||
    compactPayloadValue(payload.delta) ||
    compactPayloadValue(payload.text) ||
    compactPayloadValue(payload.output) ||
    compactPayloadValue(payload.message) ||
    compactPayloadValue(payload.reason) ||
    compactPayloadValue(payload.command) ||
    compactPayloadValue(payload.status)
  );
}

function eventBadge(event: HostRuntimeEvent): string {
  const payload = event.payload || {};
  const status = payloadText(payload, 'status');
  if (status) return status;
  if (event.event_type === 'tool.output.delta') return 'running';
  return String(payload.status || payload.reason || EVENT_LABELS[event.event_type] || event.event_type);
}

function eventRawType(event: HostRuntimeEvent): string | null {
  const payload = event.payload || {};
  const rawType = payloadText(payload, 'raw_event_type');
  if (rawType && rawType !== event.event_type) return rawType;
  return null;
}

function appendStreamDetail(current: string | null, next: string | null): string | null {
  if (!current) return next;
  if (!next) return current;
  return `${current}${/\s$/.test(current) || /^\s/.test(next) ? '' : ' '}${next}`;
}

function buildTimelineItems(events: HostRuntimeEvent[]): TimelineItem[] {
  return events.slice(-48).reduce<TimelineItem[]>((items, event, index) => {
    const title = eventTitle(event);
    const detail = eventDetail(event);
    const last = items[items.length - 1];
    if (event.event_type === 'tool.output.delta' && last?.eventType === 'tool.output.delta') {
      items[items.length - 1] = {
        ...last,
        title,
        badge: eventBadge(event),
        detail: appendStreamDetail(last.detail, detail),
      };
      return items;
    }
    return [
      ...items,
      {
        key: `${event.seq ?? 'live'}-${event.event_type}-${index}`,
        title,
        badge: eventBadge(event),
        detail,
        eventType: event.event_type,
        rawEventType: eventRawType(event),
      },
    ];
  }, []).slice(-24);
}

export function HostRuntimeEventTimeline({
  events,
}: {
  events: HostRuntimeEvent[];
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const visibleEvents = useMemo(() => buildTimelineItems(events), [events]);
  const currentEvent = visibleEvents[visibleEvents.length - 1] || null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' });
  }, [visibleEvents.length, currentEvent?.detail, currentEvent?.eventType]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" data-testid="host-runtime-event-timeline">
      {visibleEvents.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-200 p-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No host runtime events yet.
        </div>
      ) : (
        <>
          <div
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
            data-testid="host-runtime-current-activity"
          >
            <span className="font-semibold">Current:</span> {currentEvent?.title || 'Waiting'}
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-auto pr-1" data-testid="host-runtime-event-scroll">
            {visibleEvents.map((event) => (
              <div
                key={event.key}
                className="rounded-md border border-slate-200 bg-white p-2 text-xs dark:border-slate-800 dark:bg-slate-950"
                data-testid={`host-runtime-event-${event.eventType}`}
                data-event-type={event.eventType}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800 dark:text-slate-100">{event.title}</span>
                  <HostRuntimeStatusBadge status={event.badge} />
                </div>
                {event.detail ? (
                  <div className="mt-1 whitespace-pre-wrap break-words text-sm leading-5 text-slate-700 dark:text-slate-200">
                    {event.detail}
                  </div>
                ) : null}
                {event.rawEventType ? (
                  <div className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                    raw: {event.rawEventType}
                  </div>
                ) : null}
              </div>
            ))}
            <div ref={bottomRef} data-testid="host-runtime-event-bottom" />
          </div>
        </>
      )}
    </div>
  );
}
