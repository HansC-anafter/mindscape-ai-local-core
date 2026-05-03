import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';

import type { MeetingSessionSummary } from './meetingWorkbenchTypes';
import { isRecord, readString, shortId } from './meetingWorkbenchUtils';

export function readAolSessionMetadata(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const metadata = session?.metadata;
  if (!isRecord(metadata)) {
    return null;
  }

  const aolMetadata = metadata.addressable_object_layer;
  return isRecord(aolMetadata) ? aolMetadata : null;
}

function readFirstAolAttachment(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const aolMetadata = readAolSessionMetadata(session);
  const attachments = aolMetadata?.context_attachments;
  if (!Array.isArray(attachments)) {
    return null;
  }

  return attachments.find(isRecord) ?? null;
}

function readFirstAolContextEntry(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const aolMetadata = readAolSessionMetadata(session);
  const entries = aolMetadata?.context_entries;
  if (!Array.isArray(entries)) {
    return null;
  }

  return entries.find(isRecord) ?? null;
}

export function buildSessionObjectSummary(session: MeetingSessionSummary | null): AddressableObjectSummary | null {
  const attachment = readFirstAolAttachment(session);
  const contextEntry = readFirstAolContextEntry(session);
  const attachmentRef = isRecord(attachment?.object_ref) ? attachment?.object_ref : null;
  const entryRef = isRecord(contextEntry?.ref) ? contextEntry?.ref : null;
  const refSource = attachmentRef ?? entryRef;

  if (!refSource) {
    return null;
  }

  const ownerPack = readString(refSource.owner_pack);
  const objectKind = readString(refSource.object_kind);
  const objectId = readString(refSource.object_id);
  if (!ownerPack || !objectKind || !objectId) {
    return null;
  }

  const objectSummary = isRecord(attachment?.object_summary) ? attachment?.object_summary : null;
  const labels = Array.isArray(objectSummary?.labels)
    ? objectSummary.labels.filter((label): label is string => typeof label === 'string')
    : [];

  return {
    ref: {
      uri: readString(refSource.uri) || `mindscape://${ownerPack}/${objectKind}/${objectId}`,
      owner_pack: ownerPack,
      object_kind: objectKind,
      object_id: objectId,
      workspace_id: readString(refSource.workspace_id) || session?.workspace_id || null,
      version: readString(refSource.version) || null,
      selector: isRecord(refSource.selector) ? refSource.selector : null,
      source_surface: readString(refSource.source_surface) || null,
    },
    title: readString(objectSummary?.title) || objectId,
    subtitle: readString(objectSummary?.subtitle) || null,
    summary_text: readString(objectSummary?.summary_text) || null,
    status: readString(objectSummary?.status) || null,
    labels,
    owner_surface_url: readString(objectSummary?.owner_surface_url) || null,
  };
}

export function buildSessionSelection(session: MeetingSessionSummary | null): AddressableSelectionTarget | null {
  const summary = buildSessionObjectSummary(session);
  if (!summary) {
    return null;
  }

  return {
    ownerPack: summary.ref.owner_pack,
    objectKind: summary.ref.object_kind,
    objectId: summary.ref.object_id,
    version: summary.ref.version ?? undefined,
    selector: summary.ref.selector ?? undefined,
    sourceSurface: summary.ref.source_surface ?? undefined,
    label: summary.title,
    role: 'source',
  };
}

export function buildSessionAttachResponse(
  session: MeetingSessionSummary | null,
  workspaceId: string,
): ObjectMeetingAttachResponse | null {
  if (!session) {
    return null;
  }

  const aolMetadata = readAolSessionMetadata(session);
  if (!aolMetadata) {
    return null;
  }

  const entries = Array.isArray(aolMetadata.context_entries)
    ? aolMetadata.context_entries.filter(isRecord)
    : [];
  const stagedRefs = Array.isArray(aolMetadata.staged_refs)
    ? aolMetadata.staged_refs.filter(isRecord)
    : [];
  const reviewRoutes = Array.isArray(aolMetadata.review_routes)
    ? aolMetadata.review_routes.filter((route): route is string => typeof route === 'string')
    : [];
  const attachments: ObjectMeetingAttachResponse['attachments'] = [];

  entries.forEach((entry) => {
    const ref = isRecord(entry.ref) ? entry.ref : null;
    const role = readString(entry.role);
    if (!ref || !role) {
      return;
    }
    attachments.push({
      role: role as ObjectMeetingAttachResponse['attachments'][number]['role'],
      ref: {
        uri: readString(ref.uri),
        owner_pack: readString(ref.owner_pack),
        object_kind: readString(ref.object_kind),
        object_id: readString(ref.object_id),
        workspace_id: readString(ref.workspace_id) || session.workspace_id || workspaceId || null,
        version: readString(ref.version) || null,
        selector: isRecord(ref.selector) ? ref.selector : null,
        source_surface: readString(ref.source_surface) || null,
      },
      projection_level: 'meeting',
    });
  });

  return {
    workspace_id: session.workspace_id || workspaceId,
    meeting_id: session.id,
    status: readString(aolMetadata.status) === 'materialized' ? 'materialized' : 'attached',
    attachments,
    target_ref: null,
    staged_refs: stagedRefs.map((ref) => ({
      uri: readString(ref.uri),
      owner_pack: readString(ref.owner_pack),
      object_kind: readString(ref.object_kind),
      object_id: readString(ref.object_id),
      workspace_id: readString(ref.workspace_id) || session.workspace_id || workspaceId || null,
      version: readString(ref.version) || null,
      selector: isRecord(ref.selector) ? ref.selector : null,
      source_surface: readString(ref.source_surface) || null,
    })),
    review_routes: reviewRoutes,
    errors: [],
  };
}

export function getSessionDisplayTitle(session: MeetingSessionSummary): string {
  const summary = buildSessionObjectSummary(session);
  return summary?.title || session.agenda?.[0] || shortId(session.id);
}

export function getSessionSearchCorpus(session: MeetingSessionSummary): string {
  const summary = buildSessionObjectSummary(session);
  const aolMetadata = readAolSessionMetadata(session);
  const parts: string[] = [
    session.id,
    session.status ?? '',
    session.meeting_type ?? '',
    session.started_at ?? '',
    ...(session.agenda ?? []),
    summary?.title ?? '',
    summary?.subtitle ?? '',
    summary?.summary_text ?? '',
    ...(summary?.labels ?? []),
    readString(aolMetadata?.intent_summary),
  ];

  if (session.metadata) {
    try {
      parts.push(JSON.stringify(session.metadata));
    } catch {
      // Ignore non-serializable metadata; API payloads should normally be JSON.
    }
  }

  return parts.join(' ').toLowerCase();
}
