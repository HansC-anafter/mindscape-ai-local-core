'use client';

import { useEffect, useRef } from 'react';
import { eventBus } from '@/services/EventBus';
import { useLatest } from '@/hooks/useLatest';

export interface WindowEventHandlers {
  onContinueConversation?: (data: any) => void;
  onPlaybookTriggerError?: (data: any) => void;
  onAgentModeParsed?: (data: any) => void;
  onExecutionModePlaybookExecuted?: (data: any) => void;
  onExecutionResultsSummary?: (data: any) => void;
}

export interface WindowEventOptions {
  debounce?: Record<string, number>;
  enabled?: boolean;
}

/**
 * Hook for subscribing to window-level custom events via EventBus.
 *
 * Uses useLatest to stabilize handlers and options, preventing unnecessary
 * re-subscriptions when handlers/options objects change on each render.
 *
 * @param handlers - Event handlers object
 * @param options - Optional configuration (debounce times, enabled flag)
 */
export function useWindowEvents(
  handlers: WindowEventHandlers,
  options?: WindowEventOptions
) {
  const latestHandlers = useLatest(handlers);
  const latestOptions = useLatest(options);

  const cleanupRef = useRef<Array<() => void>>([]);

  useEffect(() => {
    cleanupRef.current.forEach(cleanup => cleanup());
    cleanupRef.current = [];

    if (latestOptions.current?.enabled === false) {
      return;
    }

    const unsubscribes: Array<() => void> = [];
    const currentHandlers = latestHandlers.current;
    const currentOptions = latestOptions.current;

    if (currentHandlers.onContinueConversation) {
      const unsubscribe = eventBus.subscribe(
        'continue-conversation',
        currentHandlers.onContinueConversation,
        currentOptions?.debounce?.['continue-conversation']
      );
      unsubscribes.push(unsubscribe);
    }

    if (currentHandlers.onPlaybookTriggerError) {
      const unsubscribe = eventBus.subscribe(
        'playbook-trigger-error',
        currentHandlers.onPlaybookTriggerError,
        currentOptions?.debounce?.['playbook-trigger-error']
      );
      unsubscribes.push(unsubscribe);
    }

    if (currentHandlers.onAgentModeParsed) {
      const unsubscribe = eventBus.subscribe(
        'agent-mode-parsed',
        currentHandlers.onAgentModeParsed,
        currentOptions?.debounce?.['agent-mode-parsed']
      );
      unsubscribes.push(unsubscribe);
    }

    if (currentHandlers.onExecutionModePlaybookExecuted) {
      const unsubscribe = eventBus.subscribe(
        'execution-mode-playbook-executed',
        currentHandlers.onExecutionModePlaybookExecuted,
        currentOptions?.debounce?.['execution-mode-playbook-executed']
      );
      unsubscribes.push(unsubscribe);
    }

    if (currentHandlers.onExecutionResultsSummary) {
      const unsubscribe = eventBus.subscribe(
        'execution-results-summary',
        currentHandlers.onExecutionResultsSummary,
        currentOptions?.debounce?.['execution-results-summary']
      );
      unsubscribes.push(unsubscribe);
    }

    cleanupRef.current = unsubscribes;

    return () => {
      cleanupRef.current.forEach(cleanup => cleanup());
      cleanupRef.current = [];
    };
  }, [latestHandlers, latestOptions, latestOptions.current?.enabled]);
}

