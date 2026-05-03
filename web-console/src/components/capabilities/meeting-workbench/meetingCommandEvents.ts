export const MEETING_COMMAND_LEDGER_UPDATED_EVENT = 'meeting-command-ledger-updated';

export interface MeetingCommandLedgerUpdatedDetail {
  workspaceId: string;
  meetingId: string;
  commandId: string;
  status: string;
}

export function dispatchMeetingCommandLedgerUpdated(detail: MeetingCommandLedgerUpdatedDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(MEETING_COMMAND_LEDGER_UPDATED_EVENT, { detail }));
}

export function isMeetingCommandLedgerUpdatedFor(
  event: Event,
  workspaceId: string,
  meetingId: string,
): boolean {
  const detail = event instanceof CustomEvent ? event.detail : null;
  return Boolean(
    detail &&
      detail.workspaceId === workspaceId &&
      detail.meetingId === meetingId &&
      detail.commandId,
  );
}
