'use client';

import React, { useState } from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';

import { ReferencePicker } from './ReferencePicker';

interface ReferencesSectionProps {
  apiUrl: string;
  items: ThreadBundle['references'];
  threadId: string | null;
  workspaceId: string;
  onReferenceAdded: () => void;
}

export function ReferencesSection({
  apiUrl,
  items,
  threadId,
  workspaceId,
  onReferenceAdded,
}: ReferencesSectionProps) {
  const [showPicker, setShowPicker] = useState(false);

  const handleReferenceAdded = () => {
    setShowPicker(false);
    onReferenceAdded();
  };

  const picker = showPicker && threadId ? (
    <ReferencePicker
      apiUrl={apiUrl}
      threadId={threadId}
      workspaceId={workspaceId}
      onClose={() => setShowPicker(false)}
      onReferenceAdded={handleReferenceAdded}
    />
  ) : null;

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No References</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Pin external resources such as Obsidian notes, Notion pages, and WordPress articles to this thread.
        </p>
        {threadId && (
          <button
            onClick={() => setShowPicker(true)}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Add Reference
          </button>
        )}
        {picker}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {threadId && (
        <div className="mb-4">
          <button
            onClick={() => setShowPicker(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Add Reference
          </button>
        </div>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-1">
                <a
                  href={item.uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                >
                  {item.title}
                </a>
              </h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.source_type}</span>
                {item.pinned_by && (
                  <>
                    <span>-</span>
                    <span>{item.pinned_by === 'user' ? 'Pinned by User' : 'Pinned by AI'}</span>
                  </>
                )}
              </div>
              {item.snippet && (
                <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                  {item.snippet}
                </p>
              )}
              {item.reason && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-500 italic">
                  Reason: {item.reason}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}

      {picker}
    </div>
  );
}
