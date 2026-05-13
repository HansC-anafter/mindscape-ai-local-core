import { describe, expect, it } from 'vitest';

import {
  applyMentionToken,
  buildObjectActionPlanEntries,
  buildRegistryMentionItems,
  extractMentionReferences,
  getMentionQuery,
} from './meetingMentions';
import type { MeetingMentionItem } from './meetingWorkbenchTypes';

const selectedRef = {
  uri: 'mindscape://ig/reference/ref_global',
  owner_pack: 'ig',
  object_kind: 'reference',
  object_id: 'ref_global',
};

describe('meetingMentions', () => {
  it('reads and applies the active trailing mention token', () => {
    expect(getMentionQuery('Attach this to @stor')).toBe('stor');
    expect(getMentionQuery('Attach this to @Story')).toBe('story');
    expect(getMentionQuery('Attach this to @story now')).toBeNull();
    expect(applyMentionToken('Attach this to @stor', '@storyboard:pd_manual')).toBe(
      'Attach this to @storyboard:pd_manual ',
    );
  });

  it('normalizes trailing mention query punctuation without creating raw scene refs', () => {
    expect(getMentionQuery('Compile @scene:sc07.')).toBe('scene:sc07');
    expect(getMentionQuery('Compile @scene:sc07，')).toBe('scene:sc07');
    expect(getMentionQuery('Compile @storyboard_scene:pkg:item:sc07.')).toBe('storyboard_scene:pkg:item:sc07');
    expect(extractMentionReferences('Compile @scene:sc07.', [])).toEqual([]);
  });

  it('extracts registry-backed refs and raw runtime refs without duplicating tokens', () => {
    const storyboardItem: MeetingMentionItem = {
      id: 'storyboard-pd-manual',
      kind: 'storyboard',
      label: 'PD Manual',
      token: '@storyboard:pd_manual',
      description: 'Storyboard',
      ref: {
        id: 'pd_manual',
        kind: 'storyboard',
        token: '@storyboard:pd_manual',
        label: 'PD Manual',
        description: 'Storyboard',
        uri: 'mindscape://pd/storyboard/pd_manual',
        ownerPack: 'pd',
        objectKind: 'storyboard',
      },
    };

    const refs = extractMentionReferences(
      'Use @storyboard:pd_manual and @storyboard:pd_manual through @pack:visual_audit @node:node_123',
      [storyboardItem],
    );

    expect(refs).toHaveLength(3);
    expect(refs.map((ref) => `${ref.kind}:${ref.id}`)).toEqual([
      'storyboard:pd_manual',
      'pack:visual_audit',
      'node:node_123',
    ]);
  });

  it('maps registry completion records into mention items and filters incomplete records', () => {
    const items = buildRegistryMentionItems([
      {
        token: '@storyboard_scene:pd_manual:artifact_1:sc09',
        label: 'Scene 09',
        description: 'Storyboard scene',
        ref: {
          uri: 'mindscape://pd/storyboard_scene/pd_manual:artifact_1:sc09',
          owner_pack: 'pd',
          object_kind: 'storyboard_scene',
          object_id: 'pd_manual:artifact_1:sc09',
        },
      },
      {
        token: '@broken:ref',
        label: 'Broken',
        ref: {
          owner_pack: 'pd',
          object_kind: 'storyboard',
        },
      },
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      kind: 'scene',
      token: '@storyboard_scene:pd_manual:artifact_1:sc09',
      ref: {
        id: 'pd_manual:artifact_1:sc09',
        sceneId: 'sc09',
        sessionId: 'pd_manual',
        ownerPack: 'pd',
        objectKind: 'storyboard_scene',
      },
    });
  });

  it('builds object action entries from selected source, storyboard target, and character refs', () => {
    const mentionItems = buildRegistryMentionItems([
      {
        token: '@storyboard:pd_manual',
        label: 'PD Manual',
        ref: {
          uri: 'mindscape://pd/storyboard/pd_manual',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'pd_manual',
        },
      },
      {
        token: '@character:hero_pkg',
        label: 'Hero Character',
        ref: {
          uri: 'mindscape://pd/character_package/hero_pkg',
          owner_pack: 'pd',
          object_kind: 'character_package',
          object_id: 'hero_pkg',
        },
      },
    ]);
    const refs = extractMentionReferences('Use @storyboard:pd_manual with @character:hero_pkg', mentionItems);

    expect(buildObjectActionPlanEntries(selectedRef, refs)).toEqual([
      { role: 'source', ref: selectedRef },
      {
        role: 'target',
        ref: {
          uri: 'mindscape://pd/storyboard/pd_manual',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'pd_manual',
        },
      },
      {
        role: 'character',
        ref: {
          uri: 'mindscape://pd/character_package/hero_pkg',
          owner_pack: 'pd',
          object_kind: 'character_package',
          object_id: 'hero_pkg',
        },
      },
    ]);
  });
});
