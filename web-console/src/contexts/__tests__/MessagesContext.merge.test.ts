import { describe, it, expect } from 'vitest';
import type { ChatMessage } from '@/hooks/useChatEvents';
import { mergeInitialAndStreamedMessages } from '@/contexts/MessagesContext';

function msg(partial: Partial<ChatMessage>): ChatMessage {
  return {
    id: partial.id || 'm-1',
    role: partial.role || 'assistant',
    content: partial.content || '',
    timestamp: partial.timestamp || new Date('2026-03-03T10:00:00.000Z'),
    event_type: partial.event_type,
  };
}

describe('mergeInitialAndStreamedMessages', () => {
  it('replaces optimistic user message with SSE user message', () => {
    const now = new Date('2026-03-03T10:00:10.000Z').getTime();
    const initial = [
      msg({
        id: 'user-123',
        role: 'user',
        content: '請幫我規劃品牌定位',
        timestamp: new Date('2026-03-03T10:00:00.000Z'),
      }),
    ];
    const streamed = [
      msg({
        id: 'evt-1',
        role: 'user',
        content: '請幫我規劃品牌定位',
        timestamp: new Date('2026-03-03T10:00:01.000Z'),
      }),
    ];

    const merged = mergeInitialAndStreamedMessages(initial, streamed, now);

    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('evt-1');
  });

  it('replaces optimistic assistant message with SSE assistant message', () => {
    const now = new Date('2026-03-03T10:00:20.000Z').getTime();
    const initial = [
      msg({
        id: 'assistant-123',
        role: 'assistant',
        content: '好的，我會先分析你目前的品牌調性，再提供三個可執行方向。',
        timestamp: new Date('2026-03-03T10:00:05.000Z'),
      }),
    ];
    const streamed = [
      msg({
        id: 'evt-2',
        role: 'assistant',
        content: '好的，我會先分析你目前的品牌調性，再提供三個可執行方向。',
        timestamp: new Date('2026-03-03T10:00:06.000Z'),
      }),
    ];

    const merged = mergeInitialAndStreamedMessages(initial, streamed, now);

    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('evt-2');
  });

  it('keeps non-duplicate streamed messages', () => {
    const now = new Date('2026-03-03T10:00:20.000Z').getTime();
    const initial = [
      msg({
        id: 'user-123',
        role: 'user',
        content: '第一個問題',
        timestamp: new Date('2026-03-03T10:00:00.000Z'),
      }),
    ];
    const streamed = [
      msg({
        id: 'evt-3',
        role: 'assistant',
        content: '這是不同內容的回覆',
        timestamp: new Date('2026-03-03T10:00:01.000Z'),
      }),
    ];

    const merged = mergeInitialAndStreamedMessages(initial, streamed, now);

    expect(merged).toHaveLength(2);
    expect(merged.map(m => m.id)).toEqual(['user-123', 'evt-3']);
  });
});
