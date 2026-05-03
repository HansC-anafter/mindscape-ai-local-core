export const TOOL_STATUS_EVENTS = {
  TOOL_STATUS_CHANGED: 'tool-status-changed',

  TOOL_CONFIG_UPDATED: 'tool-config-updated',

  BACKGROUND_ROUTINE_STATUS_CHANGED: 'background-routine-status-changed',
} as const;

export function dispatchToolStatusChanged(toolType?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, {
    detail: { toolType },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

export function dispatchToolConfigUpdated(toolType?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.TOOL_CONFIG_UPDATED, {
    detail: { toolType },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

export function dispatchBackgroundRoutineStatusChanged(workspaceId?: string, routineId?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.BACKGROUND_ROUTINE_STATUS_CHANGED, {
    detail: { workspaceId, routineId },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

export function listenToToolStatusChanged(
  callback: (toolType?: string) => void,
  toolType?: string
): () => void {
  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<{ toolType?: string }>;
    const eventToolType = customEvent.detail?.toolType;

    if (toolType === undefined || eventToolType === undefined || eventToolType === toolType) {
      callback(eventToolType);
    }
  };

  window.addEventListener(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, handler);

  return () => {
    window.removeEventListener(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, handler);
  };
}

export function listenToToolConfigUpdated(
  callback: (toolType?: string) => void,
  toolType?: string
): () => void {
  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<{ toolType?: string }>;
    const eventToolType = customEvent.detail?.toolType;

    if (toolType === undefined || eventToolType === undefined || eventToolType === toolType) {
      callback(eventToolType);
    }
  };

  window.addEventListener(TOOL_STATUS_EVENTS.TOOL_CONFIG_UPDATED, handler);

  return () => {
    window.removeEventListener(TOOL_STATUS_EVENTS.TOOL_CONFIG_UPDATED, handler);
  };
}

export function listenToBackgroundRoutineStatusChanged(
  callback: (workspaceId?: string, routineId?: string) => void,
  workspaceId?: string
): () => void {
  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<{ workspaceId?: string; routineId?: string }>;
    const eventWorkspaceId = customEvent.detail?.workspaceId;

    if (workspaceId === undefined || eventWorkspaceId === undefined || eventWorkspaceId === workspaceId) {
      callback(eventWorkspaceId, customEvent.detail?.routineId);
    }
  };

  window.addEventListener(TOOL_STATUS_EVENTS.BACKGROUND_ROUTINE_STATUS_CHANGED, handler);

  return () => {
    window.removeEventListener(TOOL_STATUS_EVENTS.BACKGROUND_ROUTINE_STATUS_CHANGED, handler);
  };
}
