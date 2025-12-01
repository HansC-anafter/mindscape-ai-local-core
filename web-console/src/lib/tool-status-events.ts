/**
 * Tool Status Event System
 *
 * Provides event-based mechanism for real-time tool status updates across the application.
 * Uses browser CustomEvent API for cross-component communication.
 */

export const TOOL_STATUS_EVENTS = {
  /**
   * Fired when tool connection status changes (connected, disconnected, configured, etc.)
   * Detail: { toolType?: string } - optional tool type, if omitted, all tools should refresh
   */
  TOOL_STATUS_CHANGED: 'tool-status-changed',

  /**
   * Fired when tool configuration is updated (wizard completed, connection added/removed)
   * Detail: { toolType?: string }
   */
  TOOL_CONFIG_UPDATED: 'tool-config-updated',

  /**
   * Fired when background routine readiness status changes
   * Detail: { workspaceId?: string, routineId?: string }
   */
  BACKGROUND_ROUTINE_STATUS_CHANGED: 'background-routine-status-changed',
} as const;

/**
 * Dispatch tool status changed event
 *
 * @param toolType - Optional tool type. If provided, only components using this tool should update.
 *                   If omitted, all tool-related components should refresh.
 */
export function dispatchToolStatusChanged(toolType?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, {
    detail: { toolType },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

/**
 * Dispatch tool config updated event
 *
 * @param toolType - Optional tool type
 */
export function dispatchToolConfigUpdated(toolType?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.TOOL_CONFIG_UPDATED, {
    detail: { toolType },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

/**
 * Dispatch background routine status changed event
 *
 * @param workspaceId - Optional workspace ID
 * @param routineId - Optional routine ID
 */
export function dispatchBackgroundRoutineStatusChanged(workspaceId?: string, routineId?: string): void {
  const event = new CustomEvent(TOOL_STATUS_EVENTS.BACKGROUND_ROUTINE_STATUS_CHANGED, {
    detail: { workspaceId, routineId },
    bubbles: true,
  });
  window.dispatchEvent(event);
}

/**
 * Hook helper: Listen to tool status events
 *
 * @param callback - Callback function to execute when event is fired
 * @param toolType - Optional tool type filter. If provided, only events for this tool will trigger callback.
 * @returns Cleanup function to remove event listener
 */
export function listenToToolStatusChanged(
  callback: (toolType?: string) => void,
  toolType?: string
): () => void {
  const handler = (event: Event) => {
    const customEvent = event as CustomEvent<{ toolType?: string }>;
    const eventToolType = customEvent.detail?.toolType;

    // If toolType filter is specified, only trigger for matching events or global events
    if (toolType === undefined || eventToolType === undefined || eventToolType === toolType) {
      callback(eventToolType);
    }
  };

  window.addEventListener(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, handler);

  return () => {
    window.removeEventListener(TOOL_STATUS_EVENTS.TOOL_STATUS_CHANGED, handler);
  };
}

/**
 * Hook helper: Listen to tool config updated events
 */
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

/**
 * Hook helper: Listen to background routine status changed events
 */
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

