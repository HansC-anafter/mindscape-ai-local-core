type EventHandler = (data: any) => void;
type HandlerId = string;

/**
 * Event bus for managing global custom events.
 *
 * Provides a centralized event management mechanism with support for:
 * - Event subscription and unsubscription
 * - Debouncing per event-handler combination
 * - Error isolation between handlers
 * - Cleanup mechanisms
 */
class EventBus {
  private handlers: Map<string, Map<HandlerId, EventHandler>> = new Map();
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
  private handlerIdCounter = 0;
  private handlerIdMap: WeakMap<EventHandler, HandlerId> = new WeakMap();

  /**
   * Subscribe to an event.
   *
   * @param event - Event name
   * @param handler - Event handler function
   * @param debounceMs - Optional debounce time in milliseconds
   * @returns Unsubscribe function
   */
  subscribe(event: string, handler: EventHandler, debounceMs?: number): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Map());
    }

    let handlerId = this.handlerIdMap.get(handler);
    if (!handlerId) {
      handlerId = `handler-${++this.handlerIdCounter}-${Date.now()}`;
      this.handlerIdMap.set(handler, handlerId);
    }

    const wrappedHandler = debounceMs
      ? this.debounce(event, handlerId, handler, debounceMs)
      : handler;

    this.handlers.get(event)!.set(handlerId, wrappedHandler);

    return () => {
      this.handlers.get(event)?.delete(handlerId!);
      const timerKey = `${event}:${handlerId}`;
      const timer = this.debounceTimers.get(timerKey);
      if (timer) {
        clearTimeout(timer);
        this.debounceTimers.delete(timerKey);
      }
    };
  }

  /**
   * Emit an event to all subscribed handlers.
   *
   * @param event - Event name
   * @param data - Event data
   */
  emit(event: string, data: any) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`[EventBus] Error in handler for event "${event}":`, error);
        }
      });
    }
  }

  /**
   * Debounce wrapper for event handlers.
   *
   * @param event - Event name
   * @param handlerId - Handler unique ID
   * @param fn - Original handler function
   * @param ms - Debounce time in milliseconds
   * @returns Debounced handler function
   */
  private debounce(
    event: string,
    handlerId: HandlerId,
    fn: EventHandler,
    ms: number
  ): EventHandler {
    const timerKey = `${event}:${handlerId}`;

    return (data: any) => {
      const existingTimer = this.debounceTimers.get(timerKey);
      if (existingTimer) {
        clearTimeout(existingTimer);
      }

      const newTimer = setTimeout(() => {
        try {
          fn(data);
        } catch (error) {
          console.error(`[EventBus] Error in debounced handler for event "${event}":`, error);
        } finally {
          this.debounceTimers.delete(timerKey);
        }
      }, ms);

      this.debounceTimers.set(timerKey, newTimer);
    };
  }

  /**
   * Clear all subscriptions and timers.
   */
  clear() {
    this.handlers.clear();
    this.debounceTimers.forEach(timer => clearTimeout(timer));
    this.debounceTimers.clear();
  }

  /**
   * Clear all subscriptions for a specific event.
   *
   * @param event - Event name
   */
  clearEvent(event: string) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((_, handlerId) => {
        const timerKey = `${event}:${handlerId}`;
        const timer = this.debounceTimers.get(timerKey);
        if (timer) {
          clearTimeout(timer);
          this.debounceTimers.delete(timerKey);
        }
      });
      this.handlers.delete(event);
    }
  }
}

export const eventBus = new EventBus();

/**
 * Adapter layer: Listen to window custom events and forward to EventBus.
 * This allows existing code using window.dispatchEvent to work with EventBus.
 */
if (typeof window !== 'undefined') {
  const eventNames = [
    'continue-conversation',
    'playbook-trigger-error',
    'agent-mode-parsed',
    'execution-mode-playbook-executed',
    'execution-results-summary',
  ];

  eventNames.forEach(eventName => {
    window.addEventListener(eventName, ((e: CustomEvent) => {
      eventBus.emit(eventName, e.detail);
    }) as EventListener);
  });
}

