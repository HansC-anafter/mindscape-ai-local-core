'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';

interface IntentTag {
  id: string;
  title: string;
  description?: string;
  confidence?: number;
  source: string;
  status: string;
  message_id?: string;
  created_at?: string;
}

interface IntentChipsProps {
  workspaceId: string;
  apiUrl: string;
  messageId?: string;
  onConfirm?: (intentTagId: string) => void;
}

export default function IntentChips({
  workspaceId,
  apiUrl,
  messageId,
  onConfirm
}: IntentChipsProps) {
  const [intentTags, setIntentTags] = useState<IntentTag[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  useEffect(() => {
    loadCandidateIntentTags();

    // Refresh when workspace chat updates
    const handleChatUpdate = () => {
      setTimeout(() => {
        loadCandidateIntentTags();
      }, 1000);
    };

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    return () => {
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
    };
  }, [workspaceId, messageId]);

  const loadCandidateIntentTags = async () => {
    try {
      setLoading(true);
      const url = messageId
        ? `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/candidates?message_id=${messageId}&limit=5`
        : `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/candidates?limit=5`;

      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setIntentTags(data.intent_tags || []);
      }
    } catch (err) {
      console.error('Failed to load candidate intent tags:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmIntent = async (intentTag: IntentTag) => {
    if (confirmingId) return; // Prevent multiple clicks

    setConfirmingId(intentTag.id);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${intentTag.id}/confirm`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Remove confirmed tag from list
        setIntentTags(prev => prev.filter(tag => tag.id !== intentTag.id));

        // Trigger workspace chat update to refresh
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));

        if (onConfirm) {
          onConfirm(intentTag.id);
        }
      } else {
        const error = await response.json();
        console.error('Failed to confirm intent:', error);
        alert(`Failed to confirm intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('Failed to confirm intent:', err);
      alert(`Failed to confirm intent: ${err.message || 'Unknown error'}`);
    } finally {
      setConfirmingId(null);
    }
  };

  if (loading || intentTags.length === 0) {
    return null;
  }

  return (
    <div className="px-4 pt-2 pb-1">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">
        {t('mindscapePossibleDirections') || 'Mindscape 看到的可能方向（僅供參考）'}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {intentTags.map((tag) => (
          <button
            key={tag.id}
            onClick={() => handleConfirmIntent(tag)}
            disabled={confirmingId === tag.id}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border transition-all ${
              confirmingId === tag.id
                ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-600 cursor-not-allowed'
                : 'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer'
            }`}
          >
            <span>{tag.title}</span>
            {tag.confidence && (
              <span className="text-gray-400 text-[10px]">
                {Math.round(tag.confidence * 100)}%
              </span>
            )}
            {confirmingId === tag.id && (
              <span className="text-[10px]">...</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

