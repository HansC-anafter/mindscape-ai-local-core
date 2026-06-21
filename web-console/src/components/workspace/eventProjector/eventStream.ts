import { getApiBaseUrl } from '@/lib/api-url';
import type { UnifiedEvent } from './types';

interface StreamSubscriber {
  eventTypes?: Set<string>;
  onEvent: (event: UnifiedEvent) => void;
  onError?: (error: Error) => void;
}

interface SharedStream {
  eventSource: EventSource;
  subscribers: Set<StreamSubscriber>;
  url: string;
  key: string;
}

const sharedStreams = new Map<string, SharedStream>();

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function getRuntimeEnv(name: string): string | undefined {
  const runtimeGlobal = globalThis as typeof globalThis & {
    process?: { env?: Record<string, string | undefined> };
  };
  return runtimeGlobal.process?.env?.[name];
}

function resolveEventStreamBaseUrl(apiUrl: string): string {
  const explicit = apiUrl.trim();
  if (explicit) {
    return stripTrailingSlash(explicit);
  }

  const configuredDirectUrl = (
    getRuntimeEnv('NEXT_PUBLIC_LOCAL_CORE_API_URL') ||
    getRuntimeEnv('NEXT_PUBLIC_API_URL') ||
    ''
  ).trim();
  if (configuredDirectUrl.startsWith('http')) {
    return stripTrailingSlash(configuredDirectUrl);
  }

  const fallback = getApiBaseUrl().trim();
  if (fallback) {
    return stripTrailingSlash(fallback);
  }

  if (typeof window !== 'undefined') {
    return stripTrailingSlash(window.location.origin);
  }

  return '';
}

function getOrCreateStream(workspaceId: string, apiUrl: string): SharedStream {
  const baseUrl = resolveEventStreamBaseUrl(apiUrl);
  const key = `${baseUrl}::${workspaceId}`;
  const existing = sharedStreams.get(key);
  if (existing && existing.eventSource.readyState !== EventSource.CLOSED) {
    return existing;
  }

  if (existing) {
    existing.eventSource.close();
  }

  const url = `${baseUrl}/api/v1/workspaces/${workspaceId}/events/stream`;
  const eventSource = new EventSource(url);
  const stream: SharedStream = { eventSource, subscribers: new Set(), url, key };

  const dispatch = (data: any) => {
    if (data.type === 'connected' || data.type === 'error') {
      if (data.type === 'error') {
        stream.subscribers.forEach(sub => {
          sub.onError?.(new Error(data.message));
        });
      }
      return;
    }

    const event: UnifiedEvent = {
      id: data.id,
      type: data.type,
      timestamp: data.timestamp,
      actor: data.actor,
      workspace_id: data.workspace_id,
      project_id: data.project_id,
      profile_id: data.profile_id,
      thread_id: data.thread_id || data.payload?.thread_id || data.metadata?.thread_id || data.payload?.session_id,
      payload: data.payload || data,
      entity_ids: data.entity_ids,
      metadata: data.metadata,
    };

    stream.subscribers.forEach(sub => {
      if (sub.eventTypes && sub.eventTypes.size > 0 && !sub.eventTypes.has(event.type)) {
        return;
      }
      try {
        sub.onEvent(event);
      } catch (err) {
        console.error('[EventStream] Subscriber handler error:', err);
      }
    });
  };

  const handleEvent = (event: MessageEvent) => {
    try {
      dispatch(JSON.parse(event.data));
    } catch (err) {
      console.error('[EventStream] Failed to parse event:', err, event.data);
    }
  };

  eventSource.onmessage = handleEvent;

  const allEventTypes = [
    'tool_call',
    'tool_result',
    'playbook_step',
    'insight',
    'habit_observation',
    'project_created',
    'project_updated',
    'intent_created',
    'intent_updated',
    'agent_execution',
    'execution_chat',
    'obsidian_note_updated',
    'execution_plan',
    'phase_summary',
    'pipeline_stage',
    'decision_required',
    'branch_proposed',
    'artifact_created',
    'artifact_updated',
    'run_state_changed',
    'policy_check',
    'loop_budget_exhausted',
    'quality_gate_check',
    'agent_turn',
    'decision_proposal',
    'decision_final',
    'action_item',
    'meeting_round',
    'meeting_start',
    'meeting_end',
    'memory_writeback',
    'decision_made',
    'reasoning_committed',
    'intent_patched',
    'state_vector_computed',
    'mode_transition',
    'run_started',
    'run_completed',
    'run_failed',
    'step_start',
    'step_progress',
    'step_complete',
    'step_error',
    'chunk',
    'stream_start',
    'stream_end',
    'meeting_stage',
  ];

  for (const eventType of allEventTypes) {
    eventSource.addEventListener(eventType, handleEvent);
  }

  eventSource.onerror = (err) => {
    const target = err.target as EventSource;
    if (target?.readyState === EventSource.CLOSED) {
      console.warn('[EventStream] Shared connection closed, will reconnect:', url);
    } else if (target?.readyState === EventSource.CONNECTING) {
    } else {
      console.error('[EventStream] Shared connection error:', err);
    }
  };

  eventSource.onopen = () => {
  };

  sharedStreams.set(key, stream);
  return stream;
}

export function subscribeEventStream(
  workspaceId: string,
  options: {
    apiUrl?: string;
    eventTypes?: string[];
    projectId?: string;
    onEvent: (event: UnifiedEvent) => void;
    onError?: (error: Error) => void;
  }
): () => void {
  const { apiUrl = '', eventTypes, projectId, onEvent, onError } = options;
  const stream = getOrCreateStream(workspaceId, apiUrl);

  const subscriber: StreamSubscriber = {
    eventTypes: eventTypes ? new Set(eventTypes) : undefined,
    onEvent: (event) => {
      if (projectId && event.project_id && event.project_id !== projectId) {
        return;
      }
      onEvent(event);
    },
    onError,
  };

  stream.subscribers.add(subscriber);

  return () => {
    stream.subscribers.delete(subscriber);
    if (stream.subscribers.size === 0) {
      stream.eventSource.close();
      sharedStreams.delete(stream.key);
    }
  };
}
