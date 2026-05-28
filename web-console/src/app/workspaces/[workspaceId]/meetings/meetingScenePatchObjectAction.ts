import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

import type { StoryboardScenePatchPayload } from '../../../../components/workspace/ScenePatchConsole';
import {
  invokeObjectAction,
  isPlannedObjectActionPlan,
  requestObjectActionPlan,
} from '../../../../components/capabilities/meeting-workbench/meetingObjectActions';
import type { MeetingObjectActionEntry } from '../../../../components/capabilities/meeting-workbench/meetingWorkbenchTypes';
import { isRecord, readString } from '../../../../components/capabilities/meeting-workbench/meetingWorkbenchUtils';
import type { MeetingSession } from './meetingRecords.types';

const SCENE_PATCH_AFFORDANCE_VERB = 'apply_storyboard_scene_patch';
const SCENE_PATCH_COMMAND = 'Apply storyboard scene patch';

interface ScenePatchTargetResolution {
  entry: MeetingObjectActionEntry | null;
  disabledReason: string | null;
}

export interface ApplyMeetingScenePatchObjectActionParams {
  apiUrl: string;
  workspaceId: string;
  session: MeetingSession;
  sceneId: string;
  artifactId?: string | null;
  storyboardScenePatch: StoryboardScenePatchPayload;
}

export interface ApplyMeetingScenePatchObjectActionResult {
  tone: 'success' | 'error' | 'info';
  message: string;
  payload?: Record<string, unknown>;
}

function readAolContextEntries(session: MeetingSession): Record<string, unknown>[] {
  const metadata = isRecord(session.metadata) ? session.metadata : null;
  const aolMetadata = isRecord(metadata?.addressable_object_layer)
    ? metadata?.addressable_object_layer
    : null;
  const entries = aolMetadata?.context_entries;
  return Array.isArray(entries) ? entries.filter(isRecord) : [];
}

function normalizeStoryboardSceneRef(
  value: unknown,
  workspaceId: string,
  sceneId: string,
): AddressableObjectRef | null {
  if (!isRecord(value)) {
    return null;
  }
  const selector = isRecord(value.selector) ? value.selector : null;
  const selectorSceneId = readString(selector?.scene_id);
  if (
    readString(value.object_kind) !== 'storyboard_scene' ||
    readString(selector?.selector_type) !== 'storyboard_scene' ||
    !selectorSceneId ||
    (sceneId && selectorSceneId !== sceneId)
  ) {
    return null;
  }

  const ownerPack = readString(value.owner_pack);
  const objectId = readString(value.object_id);
  if (!ownerPack || !objectId) {
    return null;
  }

  return {
    uri: readString(value.uri) || `mindscape://${ownerPack}/storyboard_scene/${objectId}`,
    owner_pack: ownerPack,
    object_kind: 'storyboard_scene',
    object_id: objectId,
    workspace_id: readString(value.workspace_id) || workspaceId,
    version: readString(value.version) || null,
    selector,
    source_surface: readString(value.source_surface) || null,
  };
}

function resolveScenePatchTarget(
  session: MeetingSession,
  workspaceId: string,
  sceneId: string,
): ScenePatchTargetResolution {
  if (!sceneId.trim()) {
    return {
      entry: null,
      disabledReason: 'scene_id is required before object-action dispatch.',
    };
  }

  const normalizedSceneId = sceneId.trim();
  for (const contextEntry of readAolContextEntries(session)) {
    const ref = normalizeStoryboardSceneRef(contextEntry.ref, workspaceId, normalizedSceneId);
    if (ref) {
      return {
        entry: {
          role: 'target',
          ref,
        },
        disabledReason: null,
      };
    }
  }

  return {
    entry: null,
    disabledReason: `No canonical storyboard_scene ObjectRef is attached for scene_id "${normalizedSceneId}".`,
  };
}

function readFirstErrorMessage(payload: Record<string, unknown> | null): string | null {
  const errors = Array.isArray(payload?.errors) ? payload?.errors : [];
  const firstError = errors.find(isRecord);
  return readString(firstError?.message) || readString(firstError?.code) || null;
}

function buildSuccessMessage(
  sceneId: string,
  invokePayload: Record<string, unknown>,
): string {
  const executorResult = isRecord(invokePayload.executor_result)
    ? invokePayload.executor_result
    : null;
  const closure = isRecord(invokePayload.closure) ? invokePayload.closure : null;
  const resultArtifact = isRecord(executorResult?.artifact)
    ? executorResult?.artifact
    : isRecord(executorResult?.result_artifact)
      ? executorResult?.result_artifact
      : null;
  const artifactId =
    readString(resultArtifact?.artifact_id) ||
    readString(executorResult?.artifact_id) ||
    readString(closure?.action_plan_id) ||
    '-';

  return [
    'Scene patch object-action completed',
    `target scene: ${sceneId || '-'}`,
    `artifact/action: ${artifactId}`,
  ].join('\n');
}

export function getMeetingScenePatchObjectActionDisabledReason(
  session: MeetingSession,
  workspaceId: string,
  sceneId: string,
): string | null {
  return resolveScenePatchTarget(session, workspaceId, sceneId).disabledReason;
}

export async function applyMeetingScenePatchObjectAction({
  apiUrl,
  workspaceId,
  session,
  sceneId,
  artifactId,
  storyboardScenePatch,
}: ApplyMeetingScenePatchObjectActionParams): Promise<ApplyMeetingScenePatchObjectActionResult> {
  const targetResolution = resolveScenePatchTarget(session, workspaceId, sceneId);
  if (!targetResolution.entry) {
    return {
      tone: 'error',
      message: targetResolution.disabledReason || 'No canonical target ObjectRef is available.',
    };
  }

  const requestContext = {
    source_surface: 'meeting_scene_patch_console',
    source_label: 'meeting_scene_patch_object_action',
    artifact_id: artifactId?.trim() || null,
    scene_id: sceneId.trim(),
    storyboard_scene_patch: storyboardScenePatch,
  };
  const objectActionContext = {
    apiUrl,
    workspaceId,
    meetingId: session.id,
    commandId: null,
    sourceSurface: 'meeting_scene_patch_console',
    selectedObjectUri: targetResolution.entry.ref.uri,
  };
  const entries = [targetResolution.entry];
  const plan = await requestObjectActionPlan(
    objectActionContext,
    SCENE_PATCH_COMMAND,
    entries,
    {
      affordanceVerb: SCENE_PATCH_AFFORDANCE_VERB,
      requestContext,
      writeMode: 'staged',
      minEntries: 1,
    },
  );

  if (!isPlannedObjectActionPlan(plan)) {
    return {
      tone: 'error',
      message: readFirstErrorMessage(plan) || 'Scene patch object-action planning failed.',
      payload: plan || undefined,
    };
  }

  const invokePayload = await invokeObjectAction(
    objectActionContext,
    SCENE_PATCH_COMMAND,
    plan,
    entries,
    {
      requestContext,
      minEntries: 1,
    },
  );

  if (readString(invokePayload.status) !== 'succeeded') {
    return {
      tone: 'error',
      message: readFirstErrorMessage(invokePayload) || 'Scene patch object-action invocation failed.',
      payload: invokePayload,
    };
  }

  return {
    tone: 'success',
    message: buildSuccessMessage(sceneId.trim(), invokePayload),
    payload: invokePayload,
  };
}
