'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';
import { linkNodeToPlaybook } from '@/lib/graph-api';

interface PlaybookLinkDialogProps {
  nodeId: string;
  onLink: (playbookCode: string) => void;
  onCancel: () => void;
}

export function PlaybookLinkDialog({ nodeId, onLink, onCancel }: PlaybookLinkDialogProps) {
  const [playbookCode, setPlaybookCode] = useState('');
  const [isLinking, setIsLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!playbookCode.trim()) return;

    setError(null);
    setIsLinking(true);

    try {
      await linkNodeToPlaybook(nodeId, playbookCode.trim());
      onLink(playbookCode.trim());
    } catch (err: any) {
      setError(err.message || t('error'));
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {t('graphNodeLinkPlaybookTitle')}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('graphNodePlaybookCodeLabel')}
            </label>
            <input
              type="text"
              value={playbookCode}
              onChange={(e) => setPlaybookCode(e.target.value)}
              placeholder={t('graphNodePlaybookCodePlaceholder')}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              required
            />
            <p className="mt-1 text-xs text-gray-500">
              {t('graphNodePlaybookCodeHint')}
            </p>
          </div>

          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              disabled={isLinking}
            >
              {t('cancel')}
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLinking || !playbookCode.trim()}
            >
              {isLinking ? t('linking') : t('link')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


