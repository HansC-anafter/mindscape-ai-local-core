/**
 * Language toggle component
 * Compact delegate to the account-backed locale provider.
 */

'use client';

import React from 'react';
import { useLocaleContext, type Locale } from '../lib/i18n';

export default function LanguageToggle() {
  const { locale, setLocale, saving, writable, error } = useLocaleContext();

  const handleLocaleChange = async (newLocale: Locale) => {
    try {
      await setLocale(newLocale);
    } catch {
      // LocaleProvider owns the user-visible error state.
    }
  };

  return (
    <div className="border-l border-gray-200 pl-4">
      <div className="flex items-center space-x-2">
        {([
          ['zh-TW', '中文'],
          ['en', 'EN'],
          ['ja', '日本語'],
        ] as const).map(([candidate, label]) => (
          <button
            key={candidate}
            onClick={() => void handleLocaleChange(candidate)}
            disabled={saving || !writable}
            className={`px-2 py-1 text-sm rounded ${
              locale === candidate
                ? 'bg-blue-500 text-white'
                : 'text-gray-600 hover:text-gray-900'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {label}
          </button>
        ))}
      </div>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
