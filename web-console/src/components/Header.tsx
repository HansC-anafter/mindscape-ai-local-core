/**
 * Header component for the web console
 * Displays app title, navigation, and language toggle
 */

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { t, useLocale, type Locale } from '../lib/i18n';

export default function Header() {
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const pathname = usePathname();
  const [locale, setLocale] = useLocale();

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
    <header className="bg-white shadow-sm border-b border-gray-200">
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
                  <span>工作區列表</span>
                </Link>
                <div className="h-4 w-px bg-gray-300"></div>
              </>
            )}
            <a
              href="/workspaces"
              className="text-gray-700 hover:text-gray-900 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navWorkspaces')}
            </a>
            <a
              href="/agents"
              className="text-gray-700 hover:text-gray-900 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navAgents')}
            </a>
          </div>

          {/* Center: Mindscape AI Workstation - Absolutely positioned for true centering */}
          <div className="absolute left-1/2 transform -translate-x-1/2" suppressHydrationWarning>
            <h1 className="text-base font-bold text-gray-900 whitespace-nowrap">
              {t('appWorkstation')}
            </h1>
          </div>

          {/* Right: Mindscape + Playbooks + System Management */}
          <nav className="flex items-center space-x-4 pr-4 flex-shrink-0 ml-auto" suppressHydrationWarning>
            <a
              href="/mindscape"
              className="text-gray-700 hover:text-gray-900 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navMindscape')}
            </a>
            <a
              href="/playbooks"
              className="text-gray-700 hover:text-gray-900 px-2 py-1 rounded-md text-xs font-medium"
            >
              {t('navPlaybooks')}
            </a>
            {/* Settings Dropdown Menu */}
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setSettingsMenuOpen(!settingsMenuOpen)}
                className="text-gray-700 hover:text-gray-900 px-2 py-1 rounded-md text-xs font-medium flex items-center"
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
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-md shadow-lg py-1 z-50 border border-gray-200">
                  <a
                    href="/settings"
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('navSettings')}
                  </a>
                  <a
                    href="/settings?tab=tools"
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('toolsAndIntegrations')}
                  </a>
                  <a
                    href="/settings?tab=packs"
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('capabilityPacks')}
                  </a>
                  <a
                    href="/history"
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    onClick={() => setSettingsMenuOpen(false)}
                  >
                    {t('navHistory')}
                  </a>
                  <div className="border-t border-gray-200 my-1"></div>
                  <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Language
                  </div>
                  <button
                    onClick={() => {
                      setLocale('zh-TW');
                      setSettingsMenuOpen(false);
                      window.location.reload();
                    }}
                    className={`w-full text-left px-4 py-2 text-sm ${
                      locale === 'zh-TW'
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-100'
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
                    className={`w-full text-left px-4 py-2 text-sm ${
                      locale === 'en'
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-100'
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
                    className={`w-full text-left px-4 py-2 text-sm ${
                      locale === 'ja'
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    日本語
                  </button>
                </div>
              )}
            </div>
          </nav>
        </div>
      </div>
    </header>
  );
}
