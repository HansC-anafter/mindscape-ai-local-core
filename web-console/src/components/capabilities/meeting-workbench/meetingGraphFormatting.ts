import type { MeetingEventSummary } from './meetingWorkbenchTypes';
import { isRecord, readString, shortId } from './meetingWorkbenchUtils';

export function truncateText(value: string, maxLength: number): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLength) {
    return cleaned;
  }

  return `${cleaned.slice(0, Math.max(0, maxLength - 1))}...`;
}

export function formatEventTime(value: string | undefined): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('sv-SE', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function formatKind(value: string | null | undefined): string {
  if (!value) {
    return 'object';
  }

  return value.replace(/_/g, ' ');
}

export function getEventMessage(event: MeetingEventSummary): string {
  const payload = isRecord(event.payload) ? event.payload : {};
  const metadata = isRecord(event.metadata) ? event.metadata : {};
  return (
    readString(payload.message) ||
    readString(payload.text) ||
    readString(payload.content) ||
    readString(payload.error) ||
    readString(metadata.message) ||
    readString(metadata.error) ||
    ''
  );
}

export function getEventType(event: MeetingEventSummary): string {
  return readString(event.event_type).toLowerCase() || 'unknown';
}

export function getEventTitle(event: MeetingEventSummary): string {
  const payload = isRecord(event.payload) ? event.payload : {};
  return (
    readString(payload.title) ||
    readString(payload.task) ||
    readString(payload.description) ||
    readString(payload.name) ||
    getEventMessage(event) ||
    readString(event.event_type) ||
    shortId(event.id)
  );
}
