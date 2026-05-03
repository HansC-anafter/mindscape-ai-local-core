import type {
  AddressableObjectRef,
  AddressableObjectRole,
  AddressableObjectSummary,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';

import type { MeetingNode, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

export type MeetingMissingContext = 'target';

function refsMatch(left: AddressableObjectRef | null | undefined, right: AddressableObjectRef | null | undefined): boolean {
  if (!left || !right) {
    return false;
  }
  if (left.uri && right.uri && left.uri === right.uri) {
    return true;
  }
  return Boolean(left.owner_pack && left.object_kind && left.object_id)
    && left.owner_pack === right.owner_pack
    && left.object_kind === right.object_kind
    && left.object_id === right.object_id;
}

function readRef(value: unknown): AddressableObjectRef | null {
  if (!isRecord(value)) {
    return null;
  }
  const ownerPack = readString(value.owner_pack);
  const objectKind = readString(value.object_kind);
  const objectId = readString(value.object_id);
  if (!ownerPack || !objectKind || !objectId) {
    return null;
  }
  return {
    uri: readString(value.uri) || `mindscape://${ownerPack}/${objectKind}/${objectId}`,
    owner_pack: ownerPack,
    object_kind: objectKind,
    object_id: objectId,
    workspace_id: readString(value.workspace_id) || undefined,
    version: readString(value.version) || undefined,
    selector: isRecord(value.selector) ? value.selector : undefined,
    source_surface: readString(value.source_surface) || undefined,
  };
}

function hasTargetContext(nodes: MeetingNode[], attachResponse: ObjectMeetingAttachResponse | null): boolean {
  if (attachResponse?.target_ref) {
    return true;
  }
  if (attachResponse?.attachments.some((attachment) => attachment.role === 'target')) {
    return true;
  }
  return nodes.some((node) => {
    const metadata = isRecord(node.metadata) ? node.metadata : {};
    if (readRef(metadata.target_ref)) {
      return true;
    }
    return readString(metadata.role) === 'target' && Boolean(readRef(metadata.ref));
  });
}

export function getMeetingWorkStatus(nodes: MeetingNode[], draftCommand: string): string {
  if (
    nodes.some((node) => node.status === 'running' && (node.kind === 'command' || node.kind === 'run'))
  ) {
    return 'Running';
  }
  if (nodes.some((node) => node.status === 'error' || node.status === 'blocked')) {
    return 'Blocked';
  }
  if (nodes.some((node) => node.kind === 'artifact' || node.lane === 'artifacts')) {
    return 'Outcome ready';
  }
  return draftCommand.trim() ? 'Drafting' : 'Ready';
}

export function getMeetingNextStepTitle(nodes: MeetingNode[]): string {
  return nodes.find((node) => node.lane === 'next')?.title || 'Ready for instruction';
}

export function getMeetingNextStepNodeId(nodes: MeetingNode[]): string | null {
  return nodes.find((node) => node.lane === 'next')?.id
    || nodes.find((node) => node.status === 'blocked' || node.status === 'error')?.id
    || nodes.find((node) => isRecord(node.metadata) && readString(node.metadata.guidance_id))?.id
    || null;
}

export function getMeetingRuntimeLabel(runtimeSnapshot: RuntimeInspectorSnapshot): string {
  if (runtimeSnapshot.loading) {
    return 'Runtime...';
  }
  return runtimeSnapshot.resolvedRuntime || runtimeSnapshot.dispatchChain[0] || 'Default runtime';
}

export function getMeetingFocusRole(
  summary: AddressableObjectSummary | null,
  attachResponse: ObjectMeetingAttachResponse | null,
): AddressableObjectRole | null {
  const focusRef = summary?.ref;
  if (!focusRef) {
    return null;
  }
  if (refsMatch(focusRef, attachResponse?.target_ref)) {
    return 'target';
  }
  const attachmentRole = attachResponse?.attachments.find((attachment) => refsMatch(focusRef, attachment.ref))?.role;
  return attachmentRole || 'source';
}

export function getMeetingMissingContext(
  nodes: MeetingNode[],
  attachResponse: ObjectMeetingAttachResponse | null,
): MeetingMissingContext | null {
  return hasTargetContext(nodes, attachResponse) ? null : 'target';
}
