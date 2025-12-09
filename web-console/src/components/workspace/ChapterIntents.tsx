'use client';

import React, { useState, useEffect } from 'react';
import type { IntentCard } from './IntentCardPanel';
import { EmptyState } from '../ui/EmptyState';
import './ChapterIntents.css';

interface ChapterIntentsProps {
  chapterId: string;
  storyThreadId: string;
  apiUrl: string;
}

export function ChapterIntents({
  chapterId,
  storyThreadId,
  apiUrl,
}: ChapterIntentsProps) {
  const [intents, setIntents] = useState<IntentCard[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadIntents();
  }, [chapterId, storyThreadId, apiUrl]);

  const loadIntents = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/story-threads/${storyThreadId}/chapters/${chapterId}/intents`
      );
      if (response.ok) {
        const data = await response.json();
        setIntents(data.intents || []);
      } else {
        setIntents([]);
      }
    } catch (err) {
      setIntents([]);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="chapter-intents-content">
        <EmptyState customMessage="Loading related decisions..." />
      </div>
    );
  }

  return (
    <div className="chapter-intents-content">
      <div className="intents-header">Related Decisions</div>
      <div className="intents-hint">
        Decisions related to this chapter's style, angle, and reader assumptions
      </div>
      {intents.length === 0 ? (
        <EmptyState customMessage="No related decisions for this chapter" />
      ) : (
        <div className="intents-list">
          {intents.map(intent => (
            <IntentCardItem key={intent.id} intent={intent} />
          ))}
        </div>
      )}
    </div>
  );
}

interface IntentCardItemProps {
  intent: IntentCard;
}

function IntentCardItem({ intent }: IntentCardItemProps) {
  const priorityColors = {
    high: 'var(--color-danger, #ef4444)',
    medium: 'var(--color-warning, #f59e0b)',
    low: 'var(--color-text-tertiary, #9ca3af)',
  };

  return (
    <div className={`intent-card-item ${intent.priority}`}>
      <div className="intent-header">
        <span className="intent-title">{intent.title}</span>
        <span
          className="priority-indicator"
          style={{ backgroundColor: priorityColors[intent.priority] }}
        />
      </div>
      {intent.description && (
        <div className="intent-description">{intent.description}</div>
      )}
      <div className="intent-status">
        Status: {intent.status === 'pending_decision' ? 'Pending' : intent.status}
      </div>
    </div>
  );
}

