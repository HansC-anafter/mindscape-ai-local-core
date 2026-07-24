import type { Dispatch, SetStateAction } from 'react';

import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectGraphProjection,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import type {
  InspectorTab,
  MeetingArtifactSummary,
  MeetingEventSummary,
  MeetingGraphEdge,
  MeetingMentionItem,
  MeetingNode,
  MeetingPackTool,
  MeetingSessionSummary,
  RuntimeInspectorSnapshot,
} from './meetingWorkbenchTypes';
import { useMeetingObjectContextData } from './useMeetingObjectContextData';
import { useMeetingObjectRegistryMentions } from './useMeetingObjectRegistryMentions';
import { useMeetingPackTools } from './useMeetingPackTools';
import { useMeetingThreadData } from './useMeetingThreadData';
import { useRuntimeInspectorSnapshot } from './useRuntimeInspectorSnapshot';
import type { MeetingProductAdmissionRequest } from '@/components/workspace-products/workspaceMeetingAdmission';

export interface MeetingWorkbenchDataState {
  activeMeetingId: string;
  setActiveMeetingId: Dispatch<SetStateAction<string>>;
  startBlankMeetingSession: (metadata?: Record<string, unknown>) => Promise<MeetingSessionSummary>;
  startingBlankMeetingSession: boolean;
  startBlankMeetingSessionError: string | null;
  meetingSessions: MeetingSessionSummary[];
  meetingSessionsLoading: boolean;
  meetingSessionsError: string | null;
  refreshMeetingSessions: () => Promise<void>;
  meetingEvents: MeetingEventSummary[];
  meetingEventsLoading: boolean;
  meetingEventsError: string | null;
  executionGraphNodes: MeetingNode[];
  executionGraphEdges: MeetingGraphEdge[];
  executionGraphLoading: boolean;
  executionGraphError: string | null;
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphNodes: MeetingNode[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  meetingArtifacts: MeetingArtifactSummary[];
  meetingArtifactsLoading: boolean;
  meetingArtifactsError: string | null;
  packTools: MeetingPackTool[];
  packToolsLoading: boolean;
  packToolsError: string | null;
  registryMentionItems: MeetingMentionItem[];
  registryMentionItemsLoading: boolean;
  registryMentionItemsError: string | null;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  effectiveAttachResponse: ObjectMeetingAttachResponse | null;
  objectTitle: string;
  objectKind: string;
  hasObjectContext: boolean;
}

export function useMeetingWorkbenchData({
  workspaceId,
  apiUrl,
  meetingId,
  summary,
  selection,
  attachResponse,
  activeMentionQuery,
  activeInspector,
  productAdmission,
}: {
  workspaceId: string;
  apiUrl: string;
  meetingId?: string | null;
  summary?: AddressableObjectSummary | null;
  selection?: AddressableSelectionTarget | null;
  attachResponse?: ObjectMeetingAttachResponse | null;
  activeMentionQuery: string | null;
  activeInspector: InspectorTab | null;
  productAdmission?: MeetingProductAdmissionRequest | null;
}): MeetingWorkbenchDataState {
  const {
    activeMeetingId,
    setActiveMeetingId,
    startBlankMeetingSession,
    startingBlankMeetingSession,
    startBlankMeetingSessionError,
    activeSession,
    meetingSessions,
    meetingSessionsLoading,
    meetingSessionsError,
    refreshMeetingSessions,
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
  } = useMeetingThreadData({
    workspaceId,
    apiUrl,
    meetingId,
    productAdmission,
  });

  const {
    objectGraphProjections,
    objectGraphNodes,
    objectGraphLoading,
    objectGraphError,
    effectiveSummary,
    effectiveSelection,
    effectiveAttachResponse,
    objectTitle,
    objectKind,
    hasObjectContext,
  } = useMeetingObjectContextData({
    workspaceId,
    apiUrl,
    activeSession,
    summary,
    selection,
    attachResponse,
  });

  const {
    packTools,
    packToolsLoading,
    packToolsError,
  } = useMeetingPackTools({ apiUrl });

  const {
    registryMentionItems,
    registryMentionItemsLoading,
    registryMentionItemsError,
  } = useMeetingObjectRegistryMentions({
    workspaceId,
    apiUrl,
    activeMeetingId,
    activeMentionQuery,
  });

  const runtimeSnapshot = useRuntimeInspectorSnapshot({
    workspaceId,
    apiUrl,
    activeInspector,
  });

  return {
    activeMeetingId,
    setActiveMeetingId,
    startBlankMeetingSession,
    startingBlankMeetingSession,
    startBlankMeetingSessionError,
    meetingSessions,
    meetingSessionsLoading,
    meetingSessionsError,
    refreshMeetingSessions,
    meetingEvents,
    meetingEventsLoading,
    meetingEventsError,
    executionGraphNodes,
    executionGraphEdges,
    executionGraphLoading,
    executionGraphError,
    objectGraphProjections,
    objectGraphNodes,
    objectGraphLoading,
    objectGraphError,
    meetingArtifacts,
    meetingArtifactsLoading,
    meetingArtifactsError,
    packTools,
    packToolsLoading,
    packToolsError,
    registryMentionItems,
    registryMentionItemsLoading,
    registryMentionItemsError,
    runtimeSnapshot,
    effectiveSummary,
    effectiveSelection,
    effectiveAttachResponse,
    objectTitle,
    objectKind,
    hasObjectContext,
  };
}
