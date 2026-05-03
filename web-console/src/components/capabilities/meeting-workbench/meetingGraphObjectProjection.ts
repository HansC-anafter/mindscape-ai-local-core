import type {
  AddressableObjectRef,
  AddressableObjectSummary,
  ObjectGuidanceCard,
  ObjectGraphProjection,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';

import { truncateText } from './meetingGraphFormatting';
import type { MeetingNode } from './meetingWorkbenchTypes';
import { safeMentionId } from './meetingWorkbenchUtils';

export function addressableRefKey(ref: AddressableObjectRef): string {
  return [ref.uri, ref.owner_pack, ref.object_kind, ref.object_id].filter(Boolean).join('|');
}

export function collectGraphProjectionRefs(
  summary: AddressableObjectSummary | null,
  attachResponse: ObjectMeetingAttachResponse | null,
): AddressableObjectRef[] {
  const refs: AddressableObjectRef[] = [];
  const seen = new Set<string>();

  function pushRef(ref: AddressableObjectRef | null | undefined) {
    if (!ref?.owner_pack || !ref.object_kind || !ref.object_id) {
      return;
    }
    const key = addressableRefKey(ref);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    refs.push(ref);
  }

  pushRef(summary?.ref);
  attachResponse?.attachments.forEach((attachment) => pushRef(attachment.ref));
  attachResponse?.staged_refs.forEach((ref) => pushRef(ref));
  return refs;
}

export function graphRefLabel(ref: AddressableObjectRef): string {
  return [ref.owner_pack, ref.object_kind, ref.object_id].filter(Boolean).join(' / ') || ref.uri || 'object';
}

export interface ObjectGuidanceDisplayCard extends ObjectGuidanceCard {
  projection: ObjectGraphProjection;
}

export interface ObjectGuidanceReviewAffordance {
  id: string;
  label: string;
  route: string;
  card: ObjectGuidanceDisplayCard;
}

export function collectObjectGuidanceCards(
  projections: ObjectGraphProjection[],
): ObjectGuidanceDisplayCard[] {
  return projections.flatMap((projection) => {
    return (projection.guidance || []).map((card) => ({
      ...card,
      projection,
    }));
  });
}

export function collectObjectGuidanceReviewAffordances(
  projections: ObjectGraphProjection[],
): ObjectGuidanceReviewAffordance[] {
  return collectObjectGuidanceCards(projections).flatMap((card) => {
    return (card.review_routes || []).map((route, index) => ({
      id: `${addressableRefKey(card.projection.ref)}-${card.id}-${index}`,
      label: card.review_label || card.title,
      route,
      card,
    }));
  });
}

export function buildObjectGraphNodes(
  projections: ObjectGraphProjection[],
  loading: boolean,
  error: string | null,
): MeetingNode[] {
  const nodes: MeetingNode[] = projections.flatMap((projection) => {
    const relationCount = projection.relations?.length ?? 0;
    const guidanceCards = projection.guidance || [];
    const title = projection.summary?.title || graphRefLabel(projection.ref);
    const relationDetail = `${relationCount} bounded relation${relationCount === 1 ? '' : 's'}`;
    const detail = guidanceCards.length > 0
      ? `${guidanceCards.length} guidance card${guidanceCards.length === 1 ? '' : 's'} · ${relationDetail}`
      : relationDetail;
    const objectNode: MeetingNode = {
      id: `object-graph-${safeMentionId(addressableRefKey(projection.ref) || title)}`,
      eyebrow: projection.node_kind || projection.ref.object_kind || 'Object',
      title: truncateText(title, 72),
      detail,
      status: relationCount > 0 || guidanceCards.length > 0 ? 'ready' : 'context',
      kind: 'object',
      lane: 'graph',
      defaultInspector: 'graph',
      childCount: guidanceCards.length || relationCount || undefined,
      output: JSON.stringify(projection, null, 2),
    };
    const guidanceNodes = guidanceCards.slice(0, 4).map((card) => ({
      id: `object-guidance-${safeMentionId(addressableRefKey(projection.ref))}-${safeMentionId(card.id || card.title)}`,
      eyebrow: card.intent || 'Guidance',
      title: truncateText(card.title, 72),
      detail: truncateText(card.description || card.command_template || graphRefLabel(projection.ref), 96),
      status: 'ready' as const,
      kind: 'group' as const,
      lane: 'graph' as const,
      defaultInspector: 'graph' as const,
      metadata: {
        guidance_id: card.id,
        guidance_intent: card.intent,
        command_template: card.command_template,
        review_label: card.review_label,
        review_routes: card.review_routes,
        proposal_ref: card.proposal_ref,
        target_ref: card.target_ref,
        required_roles: card.required_roles,
        owner_pack: projection.ref.owner_pack,
        object_kind: projection.ref.object_kind,
        object_id: projection.ref.object_id,
        object_uri: projection.ref.uri,
      },
      output: JSON.stringify(card, null, 2),
    }));
    return [objectNode, ...guidanceNodes];
  });

  if (loading || error) {
    nodes.push({
      id: 'object-graph-state',
      eyebrow: loading ? 'Object graph' : 'Object graph error',
      title: loading ? 'Loading object graph' : 'Object graph unavailable',
      detail: loading
        ? 'Reading bounded owner-pack relation projections.'
        : error || 'Failed to load object graph.',
      status: loading ? 'running' : 'error',
      kind: 'group',
      lane: 'graph',
      defaultInspector: 'graph',
    });
  }

  return nodes;
}
