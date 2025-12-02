/**
 * Internationalization (i18n) utilities
 * Supports Traditional Chinese (zh-TW), English (en), and Japanese (ja)
 *
 * ✅ MIGRATION COMPLETE ✅
 * Messages are now organized in modular structure under i18n/locales/
 * All modules have been created and aggregated in i18n/locales/index.ts
 *
 * See docs-internal/implementation/I18N_REFACTOR_MIGRATION_GUIDE.md for details.
 */

import React from 'react';
import { messages, type MessageKey } from './i18n/locales';

/**
 * Locale type derived dynamically from available locales in messages
 * This allows new locales to be automatically included once added to messages
 */
export type Locale = keyof typeof messages;

// Re-export MessageKey for backward compatibility
export type { MessageKey };

// Re-export messages from aggregated modules
export { messages };

let currentLocale: Locale = 'zh-TW';
let isClientMounted = false;

// DO NOT initialize locale from localStorage at module load time
// This ensures SSR and initial client render are always consistent
// Locale will be initialized only after client mount via useLocale hook

export function setLocale(locale: Locale): void {
  currentLocale = locale;
  if (typeof window !== 'undefined') {
    localStorage.setItem('locale', locale);
  }
}

export function getLocale(): Locale {
  // Always return 'zh-TW' during SSR and initial client render
  // This ensures hydration consistency
  // The actual locale will be applied after mount via useLocale hook
  if (typeof window === 'undefined') {
    return 'zh-TW';
  }
  // Only return stored locale after client is fully mounted
  if (!isClientMounted) {
    return 'zh-TW';
  }
  return currentLocale;
}

// Client-side function to initialize locale from localStorage
// This should only be called after component mount
export function initLocaleFromStorage(): void {
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('locale') as Locale | null;
    if (stored && (stored === 'zh-TW' || stored === 'en' || stored === 'ja')) {
      currentLocale = stored;
    }
    // Mark as mounted only after reading from localStorage
    isClientMounted = true;
  }
}

export function t(key: MessageKey, params?: Record<string, string>): string {
  // Always use 'zh-TW' during SSR and initial client render to prevent hydration mismatch
  // This ensures server-rendered HTML matches client-rendered HTML
  // After mount, components using useLocale() will re-render with the correct locale
  const locale = getLocale();
  let message = messages[locale]?.[key];
  if (message === undefined) {
    // Fallback to zh-TW if message not found
    message = messages['zh-TW']?.[key];
  }
  if (message === undefined) {
    return key;
  }
  // Replace parameters if provided
  if (params) {
    return message.replace(/\{(\w+)\}/g, (match, paramKey) => {
      return params[paramKey] || match;
    });
  }
  return message;
}

// React hook for locale management (prevents hydration mismatch)
export function useLocale(): [Locale, (locale: Locale) => void] {
  // Always initialize with 'zh-TW' to ensure SSR consistency
  // The actual locale will be loaded from localStorage after mount
  const [locale, setLocaleState] = React.useState<Locale>('zh-TW');
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    // Only after mount, read from localStorage and update state
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('locale') as Locale | null;
      if (stored && (stored === 'zh-TW' || stored === 'en' || stored === 'ja')) {
        currentLocale = stored;
        setLocaleState(stored);
      }
      // Mark as mounted after reading from localStorage
      isClientMounted = true;
      setMounted(true);
    }
  }, []);

  const updateLocale = React.useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    setLocale(newLocale);
    isClientMounted = true;
  }, []);

  // Always return 'zh-TW' until mounted to ensure SSR consistency
  // After mount, return the actual locale from state
  return [mounted ? locale : 'zh-TW', updateLocale];
}

// Updated t() function that uses locale hook if available
export function useT() {
  const [locale] = useLocale();
  return React.useCallback((key: MessageKey, params?: Record<string, string>): string => {
    let message = messages[locale]?.[key];
    if (message === undefined) {
      message = messages['zh-TW']?.[key];
    }
    if (message === undefined) {
      return key;
    }
    // Replace parameters if provided
    if (params) {
      return message.replace(/\{(\w+)\}/g, (match, paramKey) => {
        return params[paramKey] || match;
      });
    }
    return message;
  }, [locale]);
}

// Simple provider component (just passes children through)
export function LocaleProvider({ children }: { children: React.ReactNode }) {
  return React.createElement(React.Fragment, null, children);
}

// Note: Locale initialization is now handled at the top of the file
// to ensure consistency between server and client initial renders
