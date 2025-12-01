/**
 * Language toggle component
 * Allows switching between Traditional Chinese and English
 */

'use client';

import React, { useState, useEffect } from 'react';
import { useLocale, type Locale } from '../lib/i18n';

export default function LanguageToggle() {
  const [locale, setLocale] = useLocale();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleLocaleChange = (newLocale: Locale) => {
    setLocale(newLocale);
    // Force page reload to update all text
    window.location.reload();
  };

  // Always use 'zh-TW' as default locale for placeholder to ensure SSR consistency
  // This matches the initial state returned by useLocale() hook
  const displayLocale = mounted ? locale : 'zh-TW';

  // Prevent hydration mismatch by using consistent default locale
  if (!mounted) {
    return (
      <div className="flex items-center space-x-2 border-l border-gray-200 pl-4" suppressHydrationWarning>
        <button
          className="px-2 py-1 text-sm rounded bg-blue-500 text-white"
          disabled
        >
          中文
        </button>
        <button
          className="px-2 py-1 text-sm rounded text-gray-600"
          disabled
        >
          EN
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-2 border-l border-gray-200 pl-4">
      <button
        onClick={() => handleLocaleChange('zh-TW')}
        className={`px-2 py-1 text-sm rounded ${
          locale === 'zh-TW'
            ? 'bg-blue-500 text-white'
            : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        中文
      </button>
      <button
        onClick={() => handleLocaleChange('en')}
        className={`px-2 py-1 text-sm rounded ${
          locale === 'en'
            ? 'bg-blue-500 text-white'
            : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        EN
      </button>
    </div>
  );
}
