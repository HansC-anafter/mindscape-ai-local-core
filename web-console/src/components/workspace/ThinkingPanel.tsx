'use client';

import React, { useState, useEffect } from 'react';
import { ChapterOutlineView } from './ChapterOutlineView';
import { EmptyState } from '../ui/EmptyState';
import './ThinkingPanel.css';

interface SharedContext {
  theme?: string;
  key_messages?: string[];
  visual_style?: {
    colors?: string[];
  };
}

interface ThinkingPanelProps {
  workspaceId: string;
  apiUrl: string;
  storyThreadId?: string;
}

export function ThinkingPanel({
  workspaceId,
  apiUrl,
  storyThreadId,
}: ThinkingPanelProps) {
  const [sharedContext, setSharedContext] = useState<SharedContext | null>(null);
  const [loading, setLoading] = useState(!!storyThreadId);

  useEffect(() => {
    if (storyThreadId) {
      loadSharedContext();
    }
  }, [storyThreadId, apiUrl]);

  const loadSharedContext = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/story-threads/${storyThreadId}/shared-context`
      );
      if (response.ok) {
        const data = await response.json();
        setSharedContext(data.sharedContext || null);
      } else {
        setSharedContext(null);
      }
    } catch (err) {
      setSharedContext(null);
    } finally {
      setLoading(false);
    }
  };

  if (storyThreadId) {
    return (
      <div className="thinking-panel">
        <ChapterOutlineView
          storyThreadId={storyThreadId}
          apiUrl={apiUrl}
        />
      </div>
    );
  }

  return (
    <div className="thinking-panel">
      <div className="shared-context-section">
        <div className="section-header">
          <span className="title">Shared Context</span>
        </div>

        {loading ? (
          <EmptyState customMessage="Loading shared context..." />
        ) : sharedContext ? (
          <div className="context-content">
            {sharedContext.theme && (
              <div className="context-item">
                <span className="label">Theme</span>
                <span className="value">{sharedContext.theme}</span>
              </div>
            )}

            {sharedContext.key_messages && sharedContext.key_messages.length > 0 && (
              <div className="context-item">
                <span className="label">Key Messages</span>
                <ul className="message-list">
                  {sharedContext.key_messages.map((msg, i) => (
                    <li key={i}>{msg}</li>
                  ))}
                </ul>
              </div>
            )}

            {sharedContext.visual_style && sharedContext.visual_style.colors && (
              <div className="context-item">
                <span className="label">Visual Style</span>
                <div className="style-preview">
                  {sharedContext.visual_style.colors.map((color, i) => (
                    <div
                      key={i}
                      className="color-swatch"
                      style={{ backgroundColor: color }}
                      title={color}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <EmptyState customMessage="No shared context available" />
        )}
      </div>
    </div>
  );
}

