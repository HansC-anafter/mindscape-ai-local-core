import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

import { MENTION_TOKEN_PATTERN } from './meetingWorkbenchConstants';
import type {
  MeetingMentionItem,
  MeetingMentionKind,
  MeetingMentionReference,
  MeetingObjectActionEntry,
  MeetingObjectActionRole,
} from './meetingWorkbenchTypes';
import { isRecord, readString, safeMentionId, shortId } from './meetingWorkbenchUtils';

export function createMentionReference(
  item: Omit<MeetingMentionReference, 'description'> & { description?: string },
): MeetingMentionReference {
  return {
    ...item,
    description: item.description || '',
  };
}

export function getMentionQuery(command: string): string | null {
  const match = command.match(/(^|\s)@([^\s@]*)$/);
  return match ? match[2].toLowerCase() : null;
}

export function applyMentionToken(command: string, token: string): string {
  return command.replace(/(^|\s)@([^\s@]*)$/, (_match, prefix: string) => `${prefix}${token} `);
}

export function commandContainsMentionToken(command: string, token: string): boolean {
  MENTION_TOKEN_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = MENTION_TOKEN_PATTERN.exec(command)) !== null) {
    if (match[2] === token) {
      return true;
    }
  }
  return false;
}

export function parseRawMentionToken(token: string): MeetingMentionReference | null {
  const rawIdFor = (prefix: string) => {
    if (!token.startsWith(prefix)) {
      return null;
    }
    const value = token.slice(prefix.length).trim();
    return value || null;
  };

  const objectId = rawIdFor('@object:');
  if (objectId) {
    return createMentionReference({
      id: objectId,
      kind: 'object',
      token,
      label: `Object ${shortId(objectId)}`,
      description: 'Unresolved object token',
      metadata: { source: 'raw_mention_token' },
    });
  }

  const packId = rawIdFor('@pack:');
  if (packId) {
    return createMentionReference({
      id: packId,
      kind: 'pack',
      token,
      label: `Pack ${packId}`,
      description: 'Workspace pack tool',
      capabilityCode: packId.includes('.') ? packId.split('.')[0] : undefined,
      objectKind: 'playbook',
      metadata: { source: 'raw_mention_token' },
    });
  }

  const sessionId = rawIdFor('@session:');
  if (sessionId) {
    return createMentionReference({
      id: sessionId,
      kind: 'session',
      token,
      label: `Session ${shortId(sessionId)}`,
      description: 'Meeting session',
      sessionId,
      metadata: { source: 'raw_mention_token' },
    });
  }

  const nodeId = rawIdFor('@node:');
  if (nodeId) {
    return createMentionReference({
      id: nodeId,
      kind: 'node',
      token,
      label: `Node ${shortId(nodeId)}`,
      description: 'Meeting graph node',
      metadata: { source: 'raw_mention_token' },
    });
  }

  return null;
}

export function extractMentionReferences(
  command: string,
  items: MeetingMentionItem[],
): MeetingMentionReference[] {
  const seen = new Set<string>();
  const refs: MeetingMentionReference[] = [];

  function pushRef(ref: MeetingMentionReference) {
    const key = `${ref.kind}:${ref.id}:${ref.token}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    refs.push(ref);
  }

  items.forEach((item) => {
    if (!item.token || !commandContainsMentionToken(command, item.token)) {
      return;
    }

    const ref =
      item.ref ??
      createMentionReference({
        id: item.id,
        kind: item.kind,
        token: item.token,
        label: item.label,
        description: item.description,
      });

    pushRef(ref);
  });

  MENTION_TOKEN_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = MENTION_TOKEN_PATTERN.exec(command)) !== null) {
    const parsed = parseRawMentionToken(match[2]);
    if (parsed) {
      pushRef(parsed);
    }
  }

  return refs;
}

export function mentionReferenceToObjectRef(ref: MeetingMentionReference): AddressableObjectRef | null {
  if (!ref.uri || !ref.ownerPack || !ref.objectKind || !ref.id) {
    return null;
  }

  return {
    uri: ref.uri,
    owner_pack: ref.ownerPack,
    object_kind: ref.objectKind,
    object_id: ref.id,
  };
}

export function isStoryboardReference(ref: MeetingMentionReference): boolean {
  return (
    ref.kind === 'storyboard' ||
    Boolean(ref.objectKind?.startsWith('storyboard') && ref.objectKind !== 'storyboard_scene')
  );
}

export function isStoryboardSceneReference(ref: MeetingMentionReference): boolean {
  return ref.kind === 'scene' || ref.objectKind === 'storyboard_scene';
}

export function isCharacterReference(ref: MeetingMentionReference): boolean {
  return ref.kind === 'character' || Boolean(ref.objectKind?.startsWith('character'));
}

export function roleForMentionReference(ref: MeetingMentionReference): MeetingObjectActionRole | null {
  if (isStoryboardReference(ref) || isStoryboardSceneReference(ref)) {
    return 'target';
  }
  if (isCharacterReference(ref)) {
    return 'character';
  }
  if (ref.kind === 'object') {
    return 'source';
  }
  return null;
}

export function buildObjectActionPlanEntries(
  selectedObjectRef: AddressableObjectRef | null | undefined,
  mentionRefs: MeetingMentionReference[],
): MeetingObjectActionEntry[] {
  const entries: MeetingObjectActionEntry[] = [];
  const seen = new Set<string>();

  function pushEntry(role: MeetingObjectActionRole, ref: AddressableObjectRef) {
    const key = `${role}:${ref.uri}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    entries.push({ role, ref });
  }

  if (selectedObjectRef?.uri) {
    pushEntry('source', selectedObjectRef);
  }

  mentionRefs.forEach((mentionRef) => {
    const objectRef = mentionReferenceToObjectRef(mentionRef);
    const role = roleForMentionReference(mentionRef);
    if (!objectRef || !role) {
      return;
    }
    pushEntry(role, objectRef);
  });

  return entries;
}

export function mentionKindForObject(_ownerPack: string, objectKind: string): MeetingMentionKind {
  if (objectKind === 'storyboard') {
    return 'storyboard';
  }
  if (objectKind === 'storyboard_scene') {
    return 'scene';
  }
  if (objectKind.startsWith('storyboard')) {
    return 'storyboard';
  }
  if (objectKind.startsWith('character')) {
    return 'character';
  }
  return 'object';
}

export function buildRegistryMentionItems(rawItems: unknown): MeetingMentionItem[] {
  if (!Array.isArray(rawItems)) {
    return [];
  }

  return rawItems
    .filter(isRecord)
    .map((item): MeetingMentionItem | null => {
      const ref = isRecord(item.ref) ? item.ref : null;
      if (!ref) {
        return null;
      }

      const ownerPack = readString(ref.owner_pack);
      const objectKind = readString(ref.object_kind);
      const objectId = readString(ref.object_id);
      const uri = readString(ref.uri);
      if (!ownerPack || !objectKind || !objectId || !uri) {
        return null;
      }

      const token = readString(item.token) || `@object:${objectId}`;
      const label = readString(item.label) || objectId;
      const description = readString(item.description) || uri;
      const kind = mentionKindForObject(ownerPack, objectKind);
      const metadata = isRecord(item.metadata) ? item.metadata : {};
      const sceneId = objectKind === 'storyboard_scene' ? objectId.split(':').pop() || objectId : undefined;
      const sessionId = objectKind.startsWith('storyboard') ? objectId.split(':')[0] : undefined;

      return {
        id: `registry-${safeMentionId(`${ownerPack}-${objectKind}-${objectId}`)}`,
        kind,
        label,
        token,
        description,
        searchText: [
          label,
          token,
          description,
          uri,
          ownerPack,
          objectKind,
          objectId,
          readString(item.source),
        ].join(' '),
        ref: createMentionReference({
          id: objectId,
          kind,
          token,
          label,
          description,
          uri,
          ownerPack,
          objectKind,
          capabilityCode: ownerPack,
          sessionId,
          sceneId,
          packageId: objectKind === 'character_package' ? objectId : undefined,
          characterCardId: objectKind === 'character_card' ? objectId : undefined,
          metadata,
        }),
      };
    })
    .filter((item): item is MeetingMentionItem => Boolean(item));
}
