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

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function normalizeWorkspaceEvent(data: unknown): UnifiedEvent | null {
  if (!isRecord(data)) {
    return null;
  }
  const domain = data.specversion === '1.0' && isRecord(data.data)
    ? data.data
    : data;
  const type = readString(domain.event_type) || readString(data.type);
  const id = readString(data.id) || readString(domain.id);
  if (!type || !id) {
    return null;
  }
  const payload = isRecord(domain.payload) ? domain.payload : domain;
  const metadata = isRecord(domain.metadata) ? domain.metadata : undefined;
  return {
    id,
    type,
    timestamp: readString(domain.timestamp) || readString(data.time),
    actor: readString(domain.actor),
    workspace_id: readString(domain.workspace_id) || readString(data.workspaceid) || undefined,
    project_id: readString(domain.project_id) || undefined,
    profile_id: readString(domain.profile_id),
    thread_id: readString(domain.thread_id)
      || readString(payload.thread_id)
      || readString(metadata?.thread_id)
      || readString(payload.session_id)
      || undefined,
    payload,
    entity_ids: isRecord(domain.entity_ids) ? domain.entity_ids : undefined,
    metadata,
  };
}

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

  const dispatch = (data: unknown) => {
    if (isRecord(data) && (data.type === 'connected' || data.type === 'error')) {
      if (data.type === 'error') {
        stream.subscribers.forEach(sub => {
          sub.onError?.(new Error(readString(data.message)));
        });
      }
      return;
    }
    const event = normalizeWorkspaceEvent(data);
    if (!event) {
      return;
    }

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
    'capability_event',
  ];

  for (const eventType of allEventTypes) {
    eventSource.addEventListener(eventType, handleEvent);
    eventSource.addEventListener(`mindscape.workspace.${eventType}.v1`, handleEvent);
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
