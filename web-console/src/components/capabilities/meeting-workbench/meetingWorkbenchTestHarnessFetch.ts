import {
  createEmptyExecutionGraphResponse,
  createExecutionGraphResponse,
  createObjectGraphProjectResponse,
} from './meetingWorkbenchGraphFixtureResponses';
import {
  createAgentsResponse,
  createArtifactsResponse,
  createCompositionGraphCompileResponse,
  createCompositionGraphContractsResponse,
  createCompositionGraphDraftResponse,
  createCompositionGraphImportResponse,
  createCompositionGraphNodeOptionsResponse,
  createCompositionGraphRunResponse,
  createDefaultAcceptedTaskResponse,
  createEmptyArtifactsResponse,
  createEmptyEventsResponse,
  createEmptyMeetingSessionEventsResponse,
  createMeetingSessionEventsResponse,
  createMeetingSessionsResponse,
  createModelRouteRegistryResponse,
  createObjectActionInvokeResponse,
  createObjectActionPlanResponse,
  createObjectCompletionResponse,
  createPlaybooksResponse,
} from './meetingWorkbenchTestHarnessFixtures';
import { createMeetingCommandResponse } from './meetingWorkbenchTestHarnessCommandFixtures';

export function createMeetingWorkbenchTestHarnessFetch(): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes('/api/v1/playbooks/?')) {
      return createPlaybooksResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/objects/complete?')) {
      const parsedUrl = new URL(url, 'http://api.test');
      const query = (parsedUrl.searchParams.get('query') || '').toLowerCase();
      return createObjectCompletionResponse(query);
    }
    if (url.includes('/api/v1/workspaces/ws-global/object-actions/plan')) {
      return createObjectActionPlanResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/contracts')) {
      return createCompositionGraphContractsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/drafts')) {
      return createCompositionGraphDraftResponse(init);
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/import')) {
      return createCompositionGraphImportResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/node-options')) {
      return createCompositionGraphNodeOptionsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/run')) {
      return createCompositionGraphRunResponse(init);
    }
    if (url.includes('/api/v1/workspaces/ws-global/composition-graph/compile')) {
      return createCompositionGraphCompileResponse(init);
    }
    if (url.includes('/api/v1/workspaces/ws-global/meetings/mtg_global/commands')) {
      return createMeetingCommandResponse(init);
    }
    if (url.includes('/api/v1/workspaces/ws-global/object-actions/invoke')) {
      return createObjectActionInvokeResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/object-graph/project')) {
      return createObjectGraphProjectResponse(init);
    }
    if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions?limit=')) {
      return createMeetingSessionsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions/mtg_global/events?limit=120')) {
      return createMeetingSessionEventsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/meetings/mtg_global/execution-graph?limit=200')) {
      return createExecutionGraphResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/meetings/') && url.includes('/execution-graph?limit=200')) {
      return createEmptyExecutionGraphResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/artifacts?thread_id=mtg_global&limit=80')) {
      return createArtifactsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/artifacts?thread_id=')) {
      return createEmptyArtifactsResponse();
    }
    if (url.includes('/events?thread_id=')) {
      return createEmptyEventsResponse();
    }
    if (url.includes('/meeting-sessions/') && url.includes('/events?limit=120')) {
      return createEmptyMeetingSessionEventsResponse();
    }
    if (url.includes('/api/v1/workspaces/ws-global/agents')) {
      return createAgentsResponse();
    }
    if (url.includes('/api/v1/settings/model-route-registry/workspace-executor?workspace_id=ws-global')) {
      return createModelRouteRegistryResponse();
    }
    return createDefaultAcceptedTaskResponse();
  }) as typeof fetch;
}
