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

interface ObjectActionRequestOptions {
  affordanceVerb?: string | null;
  requestContext?: Record<string, unknown> | null;
  writeMode?: string | null;
  minEntries?: number;
}

function buildObjectActionRequestContext(
  context: ObjectActionContext,
  extraContext?: Record<string, unknown> | null,
) {
  return {
    source_surface: context.sourceSurface || 'meeting_graph',
    selected_object_uri: context.selectedObjectUri || null,
    command_id: context.commandId || null,
    ...(extraContext || {}),
  };
}

export async function requestObjectActionPlan(
  context: ObjectActionContext,
  trimmedCommand: string,
  entries: MeetingObjectActionEntry[],
  options: ObjectActionRequestOptions = {},
): Promise<Record<string, unknown> | null> {
  const minEntries = options.minEntries ?? 2;
  if (entries.length < minEntries) {
    return null;
  }

  try {
    const body: Record<string, unknown> = {
      instruction: trimmedCommand,
      meeting_id: context.meetingId,
      entries,
      request_context: buildObjectActionRequestContext(context, options.requestContext),
    };
    if (options.affordanceVerb) {
      body.affordance_verb = options.affordanceVerb;
    }
    if (options.writeMode) {
      body.write_mode = options.writeMode;
    }

    const response = await fetch(
      `${context.apiUrl.replace(/\/$/, '')}/api/v1/workspaces/${encodeURIComponent(
        context.workspaceId,
      )}/object-actions/plan`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
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
  options: ObjectActionRequestOptions = {},
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
      request_context: buildObjectActionRequestContext(context, options.requestContext),
    },
  );
  if (!isRecord(payload)) {
    throw new Error('Object action invocation returned an invalid response.');
  }
  return payload;
}
