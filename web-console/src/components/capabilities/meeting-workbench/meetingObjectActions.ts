import type { MeetingObjectActionEntry } from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';
import { postApiJson } from './meetingApi';

interface ObjectActionContext {
  apiUrl: string;
  workspaceId: string;
  meetingId: string;
  commandId?: string | null;
  sourceSurface: string | null | undefined;
  selectedObjectUri: string | null | undefined;
}

function buildObjectActionRequestContext(context: ObjectActionContext) {
  return {
    source_surface: context.sourceSurface || 'meeting_graph',
    selected_object_uri: context.selectedObjectUri || null,
    command_id: context.commandId || null,
  };
}

export async function requestObjectActionPlan(
  context: ObjectActionContext,
  trimmedCommand: string,
  entries: MeetingObjectActionEntry[],
): Promise<Record<string, unknown> | null> {
  if (entries.length < 2) {
    return null;
  }

  try {
    const response = await fetch(
      `${context.apiUrl.replace(/\/$/, '')}/api/v1/workspaces/${encodeURIComponent(
        context.workspaceId,
      )}/object-actions/plan`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          instruction: trimmedCommand,
          meeting_id: context.meetingId,
          entries,
          request_context: buildObjectActionRequestContext(context),
        }),
      },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return {
        status: 'rejected',
        errors: [
          {
            code: 'object_action_plan_failed',
            message: isRecord(payload?.detail)
              ? readString(payload.detail.message) || `HTTP ${response.status}`
              : `HTTP ${response.status}`,
          },
        ],
      };
    }
    return isRecord(payload) ? payload : null;
  } catch (error) {
    return {
      status: 'rejected',
      errors: [
        {
          code: 'object_action_plan_failed',
          message: error instanceof Error ? error.message : 'Failed to plan object action.',
        },
      ],
    };
  }
}

export function isPlannedObjectActionPlan(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && readString(value.status) === 'planned' && isRecord(value.request_plan);
}

export async function invokeObjectAction(
  context: ObjectActionContext,
  trimmedCommand: string,
  objectActionPlan: Record<string, unknown>,
  entries: MeetingObjectActionEntry[],
): Promise<Record<string, unknown>> {
  const payload = await postApiJson(
    context.apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(context.workspaceId)}/object-actions/invoke`,
    {
      instruction: trimmedCommand,
      meeting_id: context.meetingId,
      thread_id: context.meetingId,
      object_action_plan: objectActionPlan,
      entries,
      request_context: buildObjectActionRequestContext(context),
    },
  );
  if (!isRecord(payload)) {
    throw new Error('Object action invocation returned an invalid response.');
  }
  return payload;
}
