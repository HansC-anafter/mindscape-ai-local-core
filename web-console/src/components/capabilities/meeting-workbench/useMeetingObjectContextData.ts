import { useEffect, useMemo, useState } from 'react';

import { projectAddressableObjectGraph } from '@/lib/addressable-object-layer';
import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectGraphProjection,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import {
  addressableRefKey,
  buildObjectGraphNodes,
  collectGraphProjectionRefs,
  formatKind,
} from './meetingGraphProjection';
import {
  buildSessionAttachResponse,
  buildSessionObjectSummary,
  buildSessionSelection,
} from './meetingSessionContext';
import type { MeetingNode, MeetingSessionSummary } from './meetingWorkbenchTypes';

interface UseMeetingObjectContextDataArgs {
  workspaceId: string;
  apiUrl: string;
  activeSession: MeetingSessionSummary | null;
  summary?: AddressableObjectSummary | null;
  selection?: AddressableSelectionTarget | null;
  attachResponse?: ObjectMeetingAttachResponse | null;
}

export interface MeetingObjectContextDataState {
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphNodes: MeetingNode[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  effectiveAttachResponse: ObjectMeetingAttachResponse | null;
  objectTitle: string;
  objectKind: string;
  hasObjectContext: boolean;
}

export function useMeetingObjectContextData({
  workspaceId,
  apiUrl,
  activeSession,
  summary,
  selection,
  attachResponse,
}: UseMeetingObjectContextDataArgs): MeetingObjectContextDataState {
  const [objectGraphProjections, setObjectGraphProjections] = useState<ObjectGraphProjection[]>([]);
  const [objectGraphLoading, setObjectGraphLoading] = useState(false);
  const [objectGraphError, setObjectGraphError] = useState<string | null>(null);

  const sessionSummary = useMemo(() => buildSessionObjectSummary(activeSession), [activeSession]);
  const sessionSelection = useMemo(() => buildSessionSelection(activeSession), [activeSession]);
  const sessionAttachResponse = useMemo(
    () => buildSessionAttachResponse(activeSession, workspaceId),
    [activeSession, workspaceId],
  );
  const effectiveSummary = summary ?? sessionSummary ?? null;
  const effectiveSelection = selection ?? sessionSelection ?? null;
  const effectiveAttachResponse = attachResponse ?? sessionAttachResponse ?? null;

  const objectTitle = effectiveSummary?.title || effectiveSelection?.label || 'Selected object';
  const objectKind = formatKind(effectiveSummary?.ref.object_kind || effectiveSelection?.objectKind);
  const hasObjectContext = Boolean(effectiveSummary || effectiveSelection || effectiveAttachResponse);
  const objectGraphRefs = useMemo(
    () => collectGraphProjectionRefs(effectiveSummary, effectiveAttachResponse ?? null),
    [effectiveAttachResponse, effectiveSummary],
  );
  const objectGraphRefKey = useMemo(
    () => objectGraphRefs.map(addressableRefKey).join('\n'),
    [objectGraphRefs],
  );

  useEffect(() => {
    let cancelled = false;

    async function fetchObjectGraph() {
      if (!workspaceId || objectGraphRefs.length === 0) {
        setObjectGraphProjections([]);
        setObjectGraphError(null);
        setObjectGraphLoading(false);
        return;
      }

      setObjectGraphLoading(true);
      setObjectGraphError(null);

      try {
        const response = await projectAddressableObjectGraph({
          apiUrl,
          workspaceId,
          objects: objectGraphRefs,
          includeRelations: true,
          includeSummaries: true,
        });

        if (!cancelled) {
          setObjectGraphProjections(response.projections || []);
        }
      } catch (error) {
        if (!cancelled) {
          setObjectGraphProjections([]);
          setObjectGraphError(error instanceof Error ? error.message : 'Failed to load object graph.');
        }
      } finally {
        if (!cancelled) {
          setObjectGraphLoading(false);
        }
      }
    }

    void fetchObjectGraph();

    function handleWorkspaceUpdate() {
      void fetchObjectGraph();
    }

    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [apiUrl, objectGraphRefKey, objectGraphRefs, workspaceId]);

  const objectGraphNodes = useMemo(
    () => buildObjectGraphNodes(objectGraphProjections, objectGraphLoading, objectGraphError),
    [objectGraphError, objectGraphLoading, objectGraphProjections],
  );

  return {
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
  };
}
