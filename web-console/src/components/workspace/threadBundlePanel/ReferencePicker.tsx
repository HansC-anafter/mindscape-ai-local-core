'use client';

import React, { useState } from 'react';

import { addThreadReference } from './referenceActions';
import { referenceSourceTypes } from './sectionConfig';
import type { ThreadReferenceSourceType } from './types';

interface ReferencePickerProps {
  workspaceId: string;
  threadId: string;
  apiUrl: string;
  onClose: () => void;
  onReferenceAdded: () => void;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Failed to add reference';
}

export function ReferencePicker({
  workspaceId,
  threadId,
  apiUrl,
  onClose,
  onReferenceAdded,
}: ReferencePickerProps) {
  const [sourceType, setSourceType] = useState<ThreadReferenceSourceType | null>(null);
  const [uri, setUri] = useState('');
  const [title, setTitle] = useState('');
  const [snippet, setSnippet] = useState('');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!sourceType || !uri || !title) {
      alert('Fill in all required fields.');
      return;
    }

    setIsSubmitting(true);
    try {
      await addThreadReference({
        apiUrl,
        workspaceId,
        threadId,
        sourceType,
        uri,
        title,
        snippet,
        reason,
      });
      onReferenceAdded();
    } catch (error) {
      const message = getErrorMessage(error);
      console.error('Failed to add reference:', error);
      alert(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-white dark:bg-gray-900 rounded-lg p-6 max-w-md w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Add Reference</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {!sourceType ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Select a source type</p>
            <div className="grid grid-cols-2 gap-3">
              {referenceSourceTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setSourceType(type.value)}
                  className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left"
                >
                  <div className="text-sm font-medium">{type.label}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Source Type</label>
              <div className="flex items-center gap-2">
                <span className="text-sm">
                  {referenceSourceTypes.find((type) => type.value === sourceType)?.label}
                </span>
                <button
                  onClick={() => setSourceType(null)}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Change
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                URI <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={uri}
                onChange={(event) => setUri(event.target.value)}
                placeholder={sourceType === 'url' ? 'https://...' : sourceType === 'local_file' ? 'file://...' : 'obsidian://...'}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Reference title"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Summary</label>
              <textarea
                value={snippet}
                onChange={(event) => setSnippet(event.target.value)}
                placeholder="Short summary (optional)"
                rows={3}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Reason</label>
              <input
                type="text"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Why this resource is relevant (optional)"
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
              />
            </div>

            <div className="flex gap-2 pt-4">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || !uri || !title}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? 'Adding...' : 'Add'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
