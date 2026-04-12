import { useEffect, useMemo, useRef } from 'react';
import { subscribeEventStream } from '@/components/workspace/eventProjector';

export interface IGWorkspaceLifecycleMetadata {
  packId: string | null;
  playbookCode: string | null;
  executionId: string | null;
  lifecycleState: string | null;
  terminal: boolean;
  refreshHint: string[];
  targetUsername: string | null;
  targetHandle: string | null;
  referenceId: string | null;
  userDataDir: string | null;
  uiSurface: string | null;
  reason: string | null;
}

type WorkspaceEventShape = {
  type?: string;
  metadata?: Record<string, unknown>;
  payload?: Record<string, unknown>;
};

function readString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function readRefreshHint(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => readString(item))
      .filter((item): item is string => Boolean(item));
  }
  const single = readString(value);
  if (!single) return [];
  return single
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function getIGWorkspaceLifecycleMetadata(
  event: WorkspaceEventShape,
): IGWorkspaceLifecycleMetadata {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
  const payload = event?.payload && typeof event.payload === 'object' ? event.payload : {};

  const lifecycleState = readString(metadata.lifecycle_state ?? payload.lifecycle_state ?? payload.new_state);
  const refreshHint = readRefreshHint(metadata.refresh_hint ?? payload.refresh_hint);
  const terminal =
    metadata.terminal === true ||
    payload.terminal === true ||
    lifecycleState === 'DONE' ||
    lifecycleState === 'FAILED' ||
    lifecycleState === 'CANCELLED';

  return {
    packId: readString(metadata.pack_id ?? payload.pack_id),
    playbookCode: readString(metadata.playbook_code ?? payload.playbook_code),
    executionId: readString(metadata.execution_id ?? payload.execution_id),
    lifecycleState,
    terminal,
    refreshHint,
    targetUsername: readString(metadata.target_username ?? payload.target_username),
    targetHandle: readString(metadata.target_handle ?? payload.target_handle),
    referenceId: readString(metadata.reference_id ?? payload.reference_id),
    userDataDir: readString(metadata.user_data_dir ?? payload.user_data_dir),
    uiSurface: readString(metadata.ui_surface ?? payload.ui_surface),
    reason: readString(metadata.reason ?? payload.reason),
  };
}

export function isIGWorkspaceLifecycleEvent(event: WorkspaceEventShape): boolean {
  return event?.type === 'run_state_changed' && getIGWorkspaceLifecycleMetadata(event).packId === 'ig';
}

export function hasIGRefreshHint(
  metadata: Pick<IGWorkspaceLifecycleMetadata, 'refreshHint'>,
  hint: string,
): boolean {
  return metadata.refreshHint.includes(hint);
}

export function useIGWorkspaceEvents(params: {
  workspaceId: string;
  apiUrl?: string;
  eventTypes?: string[];
  onEvent: (event: WorkspaceEventShape, metadata: IGWorkspaceLifecycleMetadata) => void;
}) {
  const {
    workspaceId,
    apiUrl = '',
    eventTypes,
    onEvent,
  } = params;

  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const eventTypesKey = useMemo(
    () => (eventTypes && eventTypes.length > 0 ? eventTypes.join('|') : 'run_state_changed'),
    [eventTypes],
  );
  const normalizedEventTypes = useMemo(
    () => eventTypesKey.split('|').filter(Boolean),
    [eventTypesKey],
  );

  useEffect(() => {
    if (!workspaceId) return undefined;

    return subscribeEventStream(workspaceId, {
      apiUrl,
      eventTypes: normalizedEventTypes,
      onEvent: (event: WorkspaceEventShape) => {
        if (!isIGWorkspaceLifecycleEvent(event)) return;
        onEventRef.current(event, getIGWorkspaceLifecycleMetadata(event));
      },
    });
  }, [workspaceId, apiUrl, eventTypesKey, normalizedEventTypes]);
}
