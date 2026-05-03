import { useMemo } from 'react';

import type { AddressableObjectSummary } from '@/lib/addressable-object-layer';
import { createMentionReference } from './meetingMentions';
import type { MeetingMentionItem, MeetingNode, MeetingPackTool } from './meetingWorkbenchTypes';
import { shortId } from './meetingWorkbenchUtils';

interface UseMeetingMentionItemsArgs {
  activeMeetingId: string | null;
  appliedMentionItems: MeetingMentionItem[];
  effectiveSummary: AddressableObjectSummary | null;
  nodes: MeetingNode[];
  objectTitle: string;
  packTools: MeetingPackTool[];
  registryMentionItems: MeetingMentionItem[];
}

export function useMeetingMentionItems({
  activeMeetingId,
  appliedMentionItems,
  effectiveSummary,
  nodes,
  objectTitle,
  packTools,
  registryMentionItems,
}: UseMeetingMentionItemsArgs): MeetingMentionItem[] {
  return useMemo<MeetingMentionItem[]>(() => {
    const items: MeetingMentionItem[] = [];

    if (activeMeetingId) {
      const token = `@session:${shortId(activeMeetingId)}`;
      items.push({
        id: 'session-active',
        kind: 'session',
        label: `Session ${shortId(activeMeetingId)}`,
        token,
        description: 'Current meeting thread',
        searchText: `${activeMeetingId} meeting session active`,
        ref: createMentionReference({
          id: activeMeetingId,
          kind: 'session',
          token,
          label: `Session ${shortId(activeMeetingId)}`,
          description: 'Current meeting thread',
          sessionId: activeMeetingId,
          metadata: {
            active: true,
          },
        }),
      });
    }

    if (effectiveSummary?.ref.uri) {
      const token = `@object:${effectiveSummary.ref.object_id}`;
      items.push({
        id: 'object-current',
        kind: 'object',
        label: objectTitle,
        token,
        description: effectiveSummary.ref.uri,
        searchText: `${objectTitle} ${effectiveSummary.ref.uri} ${effectiveSummary.ref.object_kind} ${
          effectiveSummary.ref.owner_pack
        }`,
        ref: createMentionReference({
          id: effectiveSummary.ref.object_id,
          kind: 'object',
          token,
          label: objectTitle,
          description: effectiveSummary.ref.uri,
          uri: effectiveSummary.ref.uri,
          ownerPack: effectiveSummary.ref.owner_pack,
          objectKind: effectiveSummary.ref.object_kind,
          capabilityCode: effectiveSummary.ref.owner_pack,
          metadata: {
            source_surface: effectiveSummary.ref.source_surface,
          },
        }),
      });
    }

    appliedMentionItems.forEach((item) => {
      items.push(item);
    });

    registryMentionItems.forEach((item) => {
      items.push(item);
    });

    packTools.forEach((tool) => {
      const token = `@pack:${tool.id}`;
      items.push({
        id: `pack-${tool.id}`,
        kind: 'pack',
        label: tool.label,
        token,
        description: tool.capabilityCode ? `${tool.capabilityCode} pack tool` : tool.description,
        packToolId: tool.id,
        searchText: `${tool.label} ${tool.id} ${tool.description} ${tool.capabilityCode || ''} pack playbook tool`,
        ref: createMentionReference({
          id: tool.id,
          kind: 'pack',
          token,
          label: tool.label,
          description: tool.capabilityCode ? `${tool.capabilityCode} pack tool` : tool.description,
          ownerPack: tool.capabilityCode || undefined,
          objectKind: 'playbook',
          capabilityCode: tool.capabilityCode || undefined,
          metadata: {
            required_tools: tool.requiredTools,
          },
        }),
      });
    });

    nodes.forEach((node) => {
      const token = `@node:${node.id}`;
      items.push({
        id: `node-${node.id}`,
        kind: 'node',
        label: node.title,
        token,
        description: `${node.eyebrow} node`,
        searchText: `${node.title} ${node.detail} ${node.eyebrow} ${node.kind} ${node.lane}`,
        ref: createMentionReference({
          id: node.id,
          kind: 'node',
          token,
          label: node.title,
          description: `${node.eyebrow} node`,
          metadata: {
            node_kind: node.kind,
            lane: node.lane,
            status: node.status,
            event_ids: node.eventIds || [],
          },
        }),
      });
    });

    return items.filter((item, index, array) => {
      return array.findIndex((candidate) => candidate.token === item.token) === index;
    });
  }, [
    activeMeetingId,
    appliedMentionItems,
    effectiveSummary?.ref.object_id,
    effectiveSummary?.ref.object_kind,
    effectiveSummary?.ref.owner_pack,
    effectiveSummary?.ref.source_surface,
    effectiveSummary?.ref.uri,
    nodes,
    objectTitle,
    packTools,
    registryMentionItems,
  ]);
}
