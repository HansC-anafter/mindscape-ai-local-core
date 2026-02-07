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
import { LayoutGrid, ChevronLeft } from 'lucide-react';
import OfflineIndicator from './sync/OfflineIndicator';
import { PackListSidebar } from './workspace/PackListSidebar';

export default function Header() {
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();
  const [locale, setLocale] = useLocale();
  const { theme, setTheme } = useTheme();
  const [isPackListOpen, setIsPackListOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isWorkspacePage = pathname?.startsWith('/workspaces/');
  const isCapabilityPage = pathname?.includes('/capabilities/');
  const workspaceId = pathname?.split('/')[2];

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
    <>
      <header className="bg-surface-secondary dark:bg-gray-900 shadow-sm border-b border-default dark:border-gray-800 sticky top-0 z-50">
        <div className="w-full">
          <div className="relative flex items-center h-12">
            {/* Left: Navigation Actions */}
            <div className="flex items-center gap-2 pl-4 flex-shrink-0" suppressHydrationWarning>
              {isWorkspacePage && workspaceId && (
                <>
                  {isCapabilityPage ? (
                    /* Back to Workspace Dashboard */
                    <Link
                      href={`/workspaces/${workspaceId}`}
                      className="flex items-center text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
                    >
                      <ChevronLeft className="w-4 h-4 mr-1" />
                      <span>{t('backToWorkspace' as any) || '返回工作區'}</span>
                    </Link>
                  ) : (
                    /* Back to Workspaces List (Only show if not already on the list) */
                    pathname !== '/workspaces' && (
                      <Link
                        href="/workspaces"
                        className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors"
                      >
                        <ChevronLeft className="w-4 h-4 mr-1" />
                        <span>{t('workspaceList' as any)}</span>
                      </Link>
                    )
                  )}

                  {/* Pack List Trigger */}
                  <div className="flex items-center">
                    <div className="h-4 w-px bg-gray-300 dark:bg-gray-700 mx-2"></div>
                    <button
                      onClick={() => setIsPackListOpen(true)}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all font-medium"
                      title="Open Pack List"
                    >
                      <LayoutGrid className="w-4 h-4 text-blue-500" />
                      <span className="hidden sm:inline">Pack List</span>
                    </button>
                  </div>
                  <div className="h-4 w-px bg-gray-300 dark:bg-gray-700 ml-1 mr-2"></div>
                </>
              )}
              <a
                href="/workspaces"
                className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
              >
                {t('navWorkspaces' as any)}
              </a>
              <a
                href="/agents"
                className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
              >
                {t('navAgents' as any)}
              </a>
            </div>

            {/* Center: Mindscape AI Workstation - Absolutely positioned for true centering */}
            <div className="absolute left-1/2 transform -translate-x-1/2" suppressHydrationWarning>
              <h1 className="text-base font-bold text-gray-900 dark:text-gray-100 whitespace-nowrap">
                {t('appWorkstation' as any)}
              </h1>
            </div>

            {/* Right: Mindscape + Playbooks + System Management */}
            <nav className="flex items-center space-x-4 pr-4 flex-shrink-0 ml-auto" suppressHydrationWarning>
              <OfflineIndicator className="mr-2" />
              <a
                href="/mindscape"
                className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
              >
                {t('navMindscape' as any)}
              </a>
              <a
                href="/playbooks"
                className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium"
              >
                {t('navPlaybooks' as any)}
              </a>
              {/* Settings Dropdown Menu */}
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setSettingsMenuOpen(!settingsMenuOpen)}
                  className="text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 px-2 py-1 rounded-md text-xs font-medium flex items-center transition-colors"
                >
                  {t('navSystem' as any)}
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
                      {t('navSettings' as any)}
                    </a>
                    <a
                      href="/history"
                      className="block px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      onClick={() => setSettingsMenuOpen(false)}
                    >
                      {t('navHistory' as any)}
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
                      className={`w-full text-left px-4 py-2 text-sm transition-colors ${locale === 'zh-TW'
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
                      className={`w-full text-left px-4 py-2 text-sm transition-colors ${locale === 'en'
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
                      className={`w-full text-left px-4 py-2 text-sm transition-colors ${locale === 'ja'
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
                            <span>{t('switchToLightMode' as any)}</span>
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
                            <span>{t('switchToDarkMode' as any)}</span>
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
      {
        workspaceId && (
          <PackListSidebar
            workspaceId={workspaceId}
            isOpen={isPackListOpen}
            onClose={() => setIsPackListOpen(false)}
          />
        )
      }
    </>
  );
}
