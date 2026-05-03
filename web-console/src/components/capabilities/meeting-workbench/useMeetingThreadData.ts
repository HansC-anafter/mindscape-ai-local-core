import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';

import { subscribeEventStream, type UnifiedEvent } from '@/components/workspace/eventProjector';
import {
  isMeetingCommandLedgerUpdatedFor,
  MEETING_COMMAND_LEDGER_UPDATED_EVENT,
} from './meetingCommandEvents';
import {
  coerceExecutionGraphEdge,
  coerceExecutionGraphNode,
} from './meetingGraphProjection';
import type {
  MeetingArtifactSummary,
  MeetingEventSummary,
  MeetingExecutionGraphPayload,
  MeetingGraphEdge,
  MeetingNode,
  MeetingSessionSummary,
} from './meetingWorkbenchTypes';
import { isRecord } from './meetingWorkbenchUtils';

interface UseMeetingThreadDataArgs {
  workspaceId: string;
  apiUrl: string;
  meetingId?: string | null;
}

const MEETING_RUNTIME_REFRESH_EVENT_TYPES = [
  'message',
  'pipeline_stage',
  'action_item',
  'decision_proposal',
  'decision_final',
  'artifact_created',
  'artifact_updated',
  'run_state_changed',
  'run_started',
  'run_completed',
  'run_failed',
  'step_complete',
  'step_error',
  'tool_result',
  'meeting_stage',
  'stream_end',
];

function eventTargetsMeeting(event: UnifiedEvent, activeMeetingId: string): boolean {
  const payload: Record<string, unknown> = isRecord(event.payload) ? event.payload : {};
  const metadata: Record<string, unknown> = isRecord(event.metadata) ? event.metadata : {};
  const entityIds: Record<string, unknown> = isRecord(event.entity_ids) ? event.entity_ids : {};
  const candidates = [
    event.thread_id,
    payload['thread_id'],
    payload['session_id'],
    payload['meeting_id'],
    payload['meeting_session_id'],
    metadata['thread_id'],
    metadata['session_id'],
    metadata['meeting_id'],
    metadata['meeting_session_id'],
    ...Object.values(entityIds),
  ];

  return candidates.some((candidate) => candidate === activeMeetingId);
}

export interface MeetingThreadDataState {
  activeMeetingId: string;
  setActiveMeetingId: Dispatch<SetStateAction<string>>;
  activeSession: MeetingSessionSummary | null;
  meetingSessions: MeetingSessionSummary[];
  meetingSessionsLoading: boolean;
  meetingSessionsError: string | null;
  meetingEvents: MeetingEventSummary[];
  meetingEventsLoading: boolean;
  meetingEventsError: string | null;
  executionGraphNodes: MeetingNode[];
  executionGraphEdges: MeetingGraphEdge[];
  executionGraphLoading: boolean;
  executionGraphError: string | null;
  meetingArtifacts: MeetingArtifactSummary[];
  meetingArtifactsLoading: boolean;
  meetingArtifactsError: string | null;
}

export function useMeetingThreadData({
  workspaceId,
  apiUrl,
  meetingId,
}: UseMeetingThreadDataArgs): MeetingThreadDataState {
  const [activeMeetingId, setActiveMeetingId] = useState(meetingId ?? '');
  const [meetingSessions, setMeetingSessions] = useState<MeetingSessionSummary[]>([]);
  const [meetingSessionsLoading, setMeetingSessionsLoading] = useState(false);
  const [meetingSessionsError, setMeetingSessionsError] = useState<string | null>(null);
  const [meetingEvents, setMeetingEvents] = useState<MeetingEventSummary[]>([]);
  const [meetingEventsLoading, setMeetingEventsLoading] = useState(false);
  const [meetingEventsError, setMeetingEventsError] = useState<string | null>(null);
  const [executionGraphNodes, setExecutionGraphNodes] = useState<MeetingNode[]>([]);
  const [executionGraphEdges, setExecutionGraphEdges] = useState<MeetingGraphEdge[]>([]);
  const [executionGraphLoading, setExecutionGraphLoading] = useState(false);
  const [executionGraphError, setExecutionGraphError] = useState<string | null>(null);
  const [meetingArtifacts, setMeetingArtifacts] = useState<MeetingArtifactSummary[]>([]);
  const [meetingArtifactsLoading, setMeetingArtifactsLoading] = useState(false);
  const [meetingArtifactsError, setMeetingArtifactsError] = useState<string | null>(null);
  const [runtimeRefreshVersion, setRuntimeRefreshVersion] = useState(0);

  useEffect(() => {
    setActiveMeetingId(meetingId ?? '');
  }, [meetingId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMeetingSessions() {
      setMeetingSessionsLoading(true);
      setMeetingSessionsError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions?limit=100`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting sessions: ${response.status}`);
        }
        const data = await response.json() as { sessions?: unknown };
        if (cancelled) {
          return;
        }
        const rawSessions = Array.isArray(data.sessions) ? data.sessions : [];
        const sessions = rawSessions
          .filter(isRecord)
          .map((session: Record<string, unknown>) => session as unknown as MeetingSessionSummary);
        setMeetingSessions(sessions);
        setActiveMeetingId((current) => current || sessions[0]?.id || '');
      } catch (error) {
        if (!cancelled) {
          setMeetingSessions([]);
          setMeetingSessionsError(error instanceof Error ? error.message : 'Failed to load meeting sessions.');
        }
      } finally {
        if (!cancelled) {
          setMeetingSessionsLoading(false);
        }
      }
    }

    void fetchMeetingSessions();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, meetingId, workspaceId]);

  useEffect(() => {
    setMeetingEvents([]);
    setMeetingEventsError(null);
    setExecutionGraphNodes([]);
    setExecutionGraphEdges([]);
    setExecutionGraphError(null);
    setMeetingArtifacts([]);
    setMeetingArtifactsError(null);
  }, [activeMeetingId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchExecutionGraph() {
      if (!activeMeetingId) {
        setExecutionGraphNodes([]);
        setExecutionGraphEdges([]);
        return;
      }

      setExecutionGraphLoading(true);
      setExecutionGraphError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meetings/${encodeURIComponent(
            activeMeetingId,
          )}/execution-graph?limit=200`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting execution graph: ${response.status}`);
        }

        const data = await response.json() as MeetingExecutionGraphPayload;
        const rawNodes = Array.isArray(data.nodes) ? data.nodes : [];
        const nodes = rawNodes
          .map(coerceExecutionGraphNode)
          .filter((node): node is MeetingNode => Boolean(node));
        const rawEdges = Array.isArray(data.edges) ? data.edges : [];
        const edges = rawEdges
          .map(coerceExecutionGraphEdge)
          .filter((edge): edge is MeetingGraphEdge => Boolean(edge));

        if (!cancelled) {
          setExecutionGraphNodes(nodes);
          setExecutionGraphEdges(edges);
        }
      } catch (error) {
        if (!cancelled) {
          setExecutionGraphNodes([]);
          setExecutionGraphEdges([]);
          setExecutionGraphError(error instanceof Error ? error.message : 'Failed to load execution graph.');
        }
      } finally {
        if (!cancelled) {
          setExecutionGraphLoading(false);
        }
      }
    }

    void fetchExecutionGraph();

    function handleWorkspaceUpdate() {
      void fetchExecutionGraph();
    }

    function handleCommandLedgerUpdate(event: Event) {
      if (isMeetingCommandLedgerUpdatedFor(event, workspaceId, activeMeetingId)) {
        void fetchExecutionGraph();
      }
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);
    window.addEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
      window.removeEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);
    };
  }, [activeMeetingId, apiUrl, runtimeRefreshVersion, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function readEventsFromResponse(response: Response): Promise<MeetingEventSummary[]> {
      if (!response.ok) {
        throw new Error(`Failed to fetch meeting events: ${response.status}`);
      }
      const data = await response.json() as { events?: unknown };
      const rawEvents = Array.isArray(data.events) ? data.events : [];
      return rawEvents
        .filter(isRecord)
        .map((event: Record<string, unknown>) => event as unknown as MeetingEventSummary)
        .sort((a, b) => {
          const left = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          const right = b.timestamp ? new Date(b.timestamp).getTime() : 0;
          return left - right || a.id.localeCompare(b.id);
        });
    }

    async function fetchMeetingEvents() {
      if (!activeMeetingId) {
        setMeetingEvents([]);
        return;
      }

      setMeetingEventsLoading(true);
      setMeetingEventsError(null);

      try {
        const sessionEventsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions/${encodeURIComponent(activeMeetingId)}/events?limit=120`,
        );
        let events = await readEventsFromResponse(sessionEventsResponse);

        if (events.length === 0) {
          const threadEventsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/events?thread_id=${encodeURIComponent(activeMeetingId)}&limit=120`,
          );
          events = await readEventsFromResponse(threadEventsResponse);
        }

        if (!cancelled) {
          setMeetingEvents(events);
        }
      } catch (error) {
        if (!cancelled) {
          setMeetingEvents([]);
          setMeetingEventsError(error instanceof Error ? error.message : 'Failed to load meeting events.');
        }
      } finally {
        if (!cancelled) {
          setMeetingEventsLoading(false);
        }
      }
    }

    void fetchMeetingEvents();

    function handleWorkspaceUpdate() {
      void fetchMeetingEvents();
    }

    function handleCommandLedgerUpdate(event: Event) {
      if (isMeetingCommandLedgerUpdatedFor(event, workspaceId, activeMeetingId)) {
        void fetchMeetingEvents();
      }
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);
    window.addEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
      window.removeEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);
    };
  }, [activeMeetingId, apiUrl, runtimeRefreshVersion, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMeetingArtifacts() {
      if (!activeMeetingId) {
        setMeetingArtifacts([]);
        return;
      }

      setMeetingArtifactsLoading(true);
      setMeetingArtifactsError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/artifacts?thread_id=${encodeURIComponent(activeMeetingId)}&limit=80`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting artifacts: ${response.status}`);
        }
        const data = await response.json() as { artifacts?: unknown };
        const rawArtifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
        const artifacts = rawArtifacts
          .filter(isRecord)
          .map((artifact: Record<string, unknown>) => artifact as unknown as MeetingArtifactSummary)
          .sort((a, b) => {
            const left = a.created_at ? new Date(a.created_at).getTime() : 0;
            const right = b.created_at ? new Date(b.created_at).getTime() : 0;
            return left - right || a.id.localeCompare(b.id);
          });

        if (!cancelled) {
          setMeetingArtifacts(artifacts);
        }
      } catch (error) {
        if (!cancelled) {
          setMeetingArtifacts([]);
          setMeetingArtifactsError(error instanceof Error ? error.message : 'Failed to load meeting artifacts.');
        }
      } finally {
        if (!cancelled) {
          setMeetingArtifactsLoading(false);
        }
      }
    }

    void fetchMeetingArtifacts();

    function handleWorkspaceUpdate() {
      void fetchMeetingArtifacts();
    }

    function handleCommandLedgerUpdate(event: Event) {
      if (isMeetingCommandLedgerUpdatedFor(event, workspaceId, activeMeetingId)) {
        void fetchMeetingArtifacts();
      }
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);
    window.addEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
      window.removeEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerUpdate);
    };
  }, [activeMeetingId, apiUrl, runtimeRefreshVersion, workspaceId]);

  useEffect(() => {
    if (
      !activeMeetingId ||
      typeof window === 'undefined' ||
      typeof EventSource === 'undefined'
    ) {
      return;
    }

    return subscribeEventStream(workspaceId, {
      apiUrl,
      eventTypes: MEETING_RUNTIME_REFRESH_EVENT_TYPES,
      onEvent: (event) => {
        if (eventTargetsMeeting(event, activeMeetingId)) {
          setRuntimeRefreshVersion((current) => current + 1);
        }
      },
    });
  }, [activeMeetingId, apiUrl, workspaceId]);

  const activeSession = useMemo(
    () => meetingSessions.find((session) => session.id === activeMeetingId) ?? null,
    [activeMeetingId, meetingSessions],
  );

  return {
    activeMeetingId,
    setActiveMeetingId,
    activeSession,
    meetingSessions,
    meetingSessionsLoading,
    meetingSessionsError,
    meetingEvents,
    meetingEventsLoading,
    meetingEventsError,
    executionGraphNodes,
    executionGraphEdges,
    executionGraphLoading,
    executionGraphError,
    meetingArtifacts,
    meetingArtifactsLoading,
    meetingArtifactsError,
  };
}
