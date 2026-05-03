type EventHandler = (data: any) => void;
type HandlerId = string;

class EventBus {
  private handlers: Map<string, Map<HandlerId, EventHandler>> = new Map();
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
  private handlerIdCounter = 0;
  private handlerIdMap: WeakMap<EventHandler, HandlerId> = new WeakMap();

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

  emit(event: string, data: any) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch {
        }
      });
    }
  }

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
        } catch {
        } finally {
          this.debounceTimers.delete(timerKey);
        }
      }, ms);

      this.debounceTimers.set(timerKey, newTimer);
    };
  }

  clear() {
    this.handlers.clear();
    this.debounceTimers.forEach(timer => clearTimeout(timer));
    this.debounceTimers.clear();
  }

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
