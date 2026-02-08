'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';

interface PlaybookBlacklistManagerProps {
  blacklist: string[];
  onChange: (blacklist: string[]) => void;
}

export function PlaybookBlacklistManager({
  blacklist,
  onChange,
}: PlaybookBlacklistManagerProps) {
  const [newPlaybook, setNewPlaybook] = useState('');

  const handleAdd = () => {
    if (newPlaybook.trim() && !blacklist.includes(newPlaybook.trim())) {
      onChange([...blacklist, newPlaybook.trim()]);
      setNewPlaybook('');
    }
  };

  const handleRemove = (playbook: string) => {
    onChange(blacklist.filter((p) => p !== playbook));
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {t('playbookBlacklist' as any)}
          </h4>
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
            {t('playbookBlacklistDescription' as any)}
          </p>
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={newPlaybook}
          onChange={(e) => setNewPlaybook(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleAdd()}
          placeholder={t('enterPlaybookCode' as any)}
          className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={handleAdd}
          className="px-3 py-2 text-sm bg-red-600 dark:bg-red-700 text-white rounded hover:bg-red-700 dark:hover:bg-red-600 transition-colors"
        >
          {t('add' as any)}
        </button>
      </div>

      {blacklist.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {blacklist.map((playbook) => (
            <span
              key={playbook}
              className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 rounded text-xs"
            >
              {playbook}
              <button
                type="button"
                onClick={() => handleRemove(playbook)}
                className="hover:text-red-900 dark:hover:text-red-100"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          {t('noBlacklistedPlaybooks' as any)}
        </p>
      )}
    </div>
  );
}

