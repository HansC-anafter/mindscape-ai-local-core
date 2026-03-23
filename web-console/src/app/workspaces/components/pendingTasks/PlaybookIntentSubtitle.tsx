'use client';

import React, { useEffect, useState } from 'react';

import { useT } from '@/lib/i18n';

interface PlaybookIntentSubtitleProps {
  workspaceId: string;
  apiUrl: string;
  messageId: string;
}

export default function PlaybookIntentSubtitle({
  workspaceId,
  apiUrl,
  messageId,
}: PlaybookIntentSubtitleProps) {
  const t = useT();
  const [intentTag, setIntentTag] = useState<any>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedLabel, setEditedLabel] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchIntentTag = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/candidates?message_id=${messageId}&limit=1`
        );
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (data.intent_tags && data.intent_tags.length > 0) {
          setIntentTag(data.intent_tags[0]);
          setEditedLabel(data.intent_tags[0].title);
        }
      } catch (error) {
        console.error('Failed to fetch intent tag:', error);
      } finally {
        setLoading(false);
      }
    };

    void fetchIntentTag();
  }, [apiUrl, messageId, workspaceId]);

  const handleSaveEdit = async () => {
    if (!intentTag || !editedLabel.trim()) {
      return;
    }

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${intentTag.id}/label`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: editedLabel.trim() }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        alert(`Failed to update label: ${error.detail || t('unknownError' as any)}`);
        return;
      }

      setIsEditing(false);
      setIntentTag({ ...intentTag, title: editedLabel.trim() });
      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
    } catch (error: any) {
      console.error('Failed to update intent tag label:', error);
      alert(`Failed to update label: ${error.message || t('unknownError' as any)}`);
    }
  };

  if (loading || !intentTag) {
    return null;
  }

  return (
    <div className="mb-1.5 flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
      <span>{t('intentBasedOnAISuggestion' as any)}</span>
      {isEditing ? (
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={editedLabel}
            onChange={(event) => setEditedLabel(event.target.value)}
            className="min-w-0 flex-1 rounded border border-gray-300 bg-white px-1 py-0.5 text-[10px] text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:focus:ring-blue-400"
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                void handleSaveEdit();
              } else if (event.key === 'Escape') {
                setIsEditing(false);
                setEditedLabel(intentTag.title);
              }
            }}
            autoFocus
          />
          <button
            onClick={() => void handleSaveEdit()}
            className="text-[10px] text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
          >
            {t('save' as any)}
          </button>
          <button
            onClick={() => {
              setIsEditing(false);
              setEditedLabel(intentTag.title);
            }}
            className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
          >
            {t('cancel' as any)}
          </button>
        </div>
      ) : (
        <>
          <span className="font-medium">{intentTag.title}</span>
          <button
            onClick={() => setIsEditing(true)}
            className="text-[10px] text-gray-400 transition-colors hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            title={t('editIntentLabel' as any)}
          >
            {t('edit' as any)}
          </button>
        </>
      )}
    </div>
  );
}
