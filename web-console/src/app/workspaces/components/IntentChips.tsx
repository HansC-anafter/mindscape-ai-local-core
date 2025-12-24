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
    if (confirmingId) {
      console.log('[IntentChips] Already confirming, ignoring click');
      return; // Prevent multiple clicks
    }

    console.log('[IntentChips] Confirming intent:', {
      intentTagId: intentTag.id,
      title: intentTag.title,
      workspaceId,
      apiUrl
    });

    setConfirmingId(intentTag.id);

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${intentTag.id}/confirm`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        }
      );

      console.log('[IntentChips] Confirm response:', {
        status: response.status,
        statusText: response.statusText,
        ok: response.ok
      });

      if (response.ok) {
        const data = await response.json().catch(() => ({}));
        console.log('[IntentChips] Confirm success:', data);

        // Remove confirmed tag from list
        setIntentTags(prev => prev.filter(tag => tag.id !== intentTag.id));

        // Trigger workspace chat update to refresh
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));

        // Trigger continue-conversation event to guide user to chat window
        window.dispatchEvent(new CustomEvent('continue-conversation', {
          detail: {
            type: 'continue-conversation',
            intentId: intentTag.id,
            context: {
              topic: intentTag.title,
              suggestedMessage: `關於「${intentTag.title}」，我想要進一步討論...`
            }
          }
        }));

        if (onConfirm) {
          onConfirm(intentTag.id);
        }
      } else {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('[IntentChips] Failed to confirm intent:', error);
        alert(`Failed to confirm intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('[IntentChips] Error confirming intent:', err);
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
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              console.log('[IntentChips] Button clicked:', { tagId: tag.id, title: tag.title });
              handleConfirmIntent(tag);
            }}
            disabled={confirmingId === tag.id || confirmingId !== null}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border transition-all ${
              confirmingId === tag.id
                ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700 cursor-not-allowed animate-pulse'
                : 'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer active:bg-blue-50 dark:active:bg-blue-900/30'
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

