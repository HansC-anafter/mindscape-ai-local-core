/**
 * Header component for the web console
 * Displays app title, navigation, and language toggle
 */

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { t, useLocale, type Locale } from '../lib/i18n';
import { useTheme } from 'next-themes';
import OfflineIndicator from './sync/OfflineIndicator';

export default function Header() {
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();
  const [locale, setLocale] = useLocale();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  const isWorkspacePage = pathname?.startsWith('/workspaces/');

  // Use default t() function to ensure consistency during SSR and initial render
  // Only use useT() after mount if needed, but for now stick with t() for consistency

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setSettingsMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <header className="bg-white dark:bg-gray-900 shadow-sm border-b border-gray-200 dark:border-gray-800 sticky top-0 z-50">
      <div className="w-full">
        <div className="relative flex items-center h-12">
          {/* Left: Workspace List + Workspaces + AI Team */}
          <div className="flex items-center gap-3 pl-4 flex-shrink-0" suppressHydrationWarning>
            {isWorkspacePage && (
              <>
                <Link
                  href="/workspaces"
                  className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors"
                >
                  <svg
                    className="w-4 h-4 mr-1"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 19l-7-7 7-7"
                    />
                  </svg>
                  <span>{t('workspaceList')}</span>
                </Link>
                <div className="h-4 w-px bg-gray-300"></div>
              </>
            )}
            <a
              href="/workspaces"
              className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navWorkspaces')}
            </a>
            <a
              href="/agents"
              className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navAgents')}
            </a>
          </div>

          {/* Center: Mindscape AI Workstation - Absolutely positioned for true centering */}
          <div className="absolute left-1/2 transform -translate-x-1/2" suppressHydrationWarning>
            <h1 className="text-base font-bold text-gray-900 dark:text-gray-100 whitespace-nowrap">
              {t('appWorkstation')}
            </h1>
          </div>

          {/* Right: Mindscape + Playbooks + System Management */}
          <nav className="flex items-center space-x-4 pr-4 flex-shrink-0 ml-auto" suppressHydrationWarning>
            <OfflineIndicator className="mr-2" />
            <a
              href="/mindscape"
              className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navMindscape')}
            </a>
            <a
              href="/playbooks"
              className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navPlaybooks')}
            </a>
            {/* Settings Dropdown Menu */}
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setSettingsMenuOpen(!settingsMenuOpen)}
                className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium flex items-center transition-colors"
              >
                {t('navSystem')}
                <svg
                  className={`ml-1 h-4 w-4 transition-transform ${settingsMenuOpen ? 'transform rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Dropdown Menu */}
              {settingsMenuOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-md shadow-lg py-1 z-50 border border-gray-200 dark:border-gray-700">
                  <a
                    href="/settings"
                    className="block px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('navSettings')}
                  </a>
                  <a
                    href="/history"
                    className="block px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('navHistory')}
                  </a>
                  <div className="border-t border-gray-200 dark:border-gray-700 my-1"></div>
                  <div className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Language
                  </div>
                  <button
                    onClick={() => {
                      setLocale('zh-TW');
                      setSettingsMenuOpen(false);
                      window.location.reload();
                    }}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                      locale === 'zh-TW'
                        ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
                  >
                    中文
                  </button>
                  <button
                    onClick={() => {
                      setLocale('en');
                      setSettingsMenuOpen(false);
                      window.location.reload();
                    }}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                      locale === 'en'
                        ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
                  >
                    English
                  </button>
                  <button
                    onClick={() => {
                      setLocale('ja');
                      setSettingsMenuOpen(false);
                      window.location.reload();
                    }}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                      locale === 'ja'
                        ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
                  >
                    日本語
                  </button>
                  <div className="border-t border-gray-200 dark:border-gray-700 my-1"></div>
                  {mounted && (
                    <button
                      onClick={() => {
                        setTheme(theme === 'dark' ? 'light' : 'dark');
                      }}
                      className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
                    >
                      {theme === 'dark' ? (
                        <>
                          <svg
                            className="w-4 h-4 text-yellow-500"
                            fill="none"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                          </svg>
                          <span>{t('switchToLightMode')}</span>
                        </>
                      ) : (
                        <>
                          <svg
                            className="w-4 h-4 text-gray-700 dark:text-gray-300"
                            fill="none"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                          </svg>
                          <span>{t('switchToDarkMode')}</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              )}
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
}
