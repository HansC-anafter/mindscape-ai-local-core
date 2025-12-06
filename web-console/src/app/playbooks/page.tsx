'use client';

import React, { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Header from '../../components/Header';
import { t, useLocale } from '../../lib/i18n';
import { getPlaybookMetadata } from '../../lib/i18n/locales/playbooks';
import PlaybookDiscoveryChat from '../../components/playbook/PlaybookDiscoveryChat';
import { getPlaybookRegistry } from '../../playbook';
import ForkPlaybookButton from '../../components/playbooks/ForkPlaybookButton';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Playbook {
  playbook_code: string;
  version: string;
  locale: string;
  name: string;
  description: string;
  tags: string[];
  icon?: string;
  entry_agent_type?: string;
  onboarding_task?: string;
  required_tools: string[];
  kind?: string;
  scope?: 'system' | 'tenant' | 'profile' | 'workspace';
  user_meta: {
    favorite: boolean;
    use_count: number;
  };
  has_personal_variant?: boolean;
  default_variant_name?: string;
}

export default function PlaybooksPage() {
  const [locale] = useLocale();
  const router = useRouter();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [supportedTestPlaybooks, setSupportedTestPlaybooks] = useState<Set<string>>(new Set());
  const [creatingWorkspace, setCreatingWorkspace] = useState<string | null>(null);

  // Load supported test playbooks
  useEffect(() => {
    const loadSupportedTests = async () => {
      try {
        const apiUrl = API_URL.startsWith('http') ? API_URL : '';
        const response = await fetch(`${apiUrl}/api/v1/playbooks/smoke-test/supported`);
        if (response.ok) {
          const data = await response.json();
          setSupportedTestPlaybooks(new Set(data));
        }
      } catch (err) {
        console.error('Failed to load supported test playbooks:', err);
      }
    };
    loadSupportedTests();
  }, []);

  // Load playbooks when component mounts or when selectedTags changes
  useEffect(() => {
    let isMounted = true;

    const loadPlaybooks = async () => {
      try {
        setLoading(true);
        const apiUrl = API_URL.startsWith('http') ? API_URL : '';
        const tags = selectedTags.join(',');
        // Use locale from useLocale hook to determine target_language
        // This ensures we get the actual user-selected language
        const targetLanguage = locale === 'en' ? 'en' : locale === 'ja' ? 'ja' : 'zh-TW';
        const url = `${apiUrl}/api/v1/playbooks?tags=${tags}&target_language=${targetLanguage}&profile_id=default-user`;

        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          // Ensure data is an array and has required fields
          const validPlaybooks = Array.isArray(data) ? data.filter(p =>
            p && p.playbook_code && p.name
          ) : [];

          if (isMounted) {
            setPlaybooks(validPlaybooks);
            setError(null);
          }
        } else {
          throw new Error('Failed to load playbooks');
        }
      } catch (err: any) {
        console.error('Failed to load playbooks:', err);
        if (isMounted) {
          setError(err.message);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadPlaybooks();

    return () => {
      isMounted = false;
    };
  }, [selectedTags, locale]);

  const toggleFavorite = async (playbookCode: string, currentFavorite: boolean) => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      await fetch(`${apiUrl}/api/v1/playbooks/${playbookCode}/meta?profile_id=default-user&favorite=${!currentFavorite}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      });
      // Reload playbooks by updating selectedTags (triggers useEffect)
      setSelectedTags(prev => [...prev]);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  };

  const handleExecuteNow = async (e: React.MouseEvent, playbook: Playbook) => {
    e.preventDefault();
    e.stopPropagation();

    if (creatingWorkspace) return;

    try {
      setCreatingWorkspace(playbook.playbook_code);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const ownerUserId = 'default-user';

      // Generate workspace name: playbook_code_YYYYMMDD_HHMMSS
      const now = new Date();
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      const seconds = String(now.getSeconds()).padStart(2, '0');
      const workspaceTitle = `${playbook.playbook_code}_${year}${month}${day}_${hours}${minutes}${seconds}`;

      // Create workspace
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces?owner_user_id=${ownerUserId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            title: workspaceTitle,
            description: `Workspace for ${playbook.name}`
          })
        }
      );

      if (response.ok) {
        const newWorkspace = await response.json();

        // Check if playbook has UI Surface
        const registry = getPlaybookRegistry();
        const playbookPackage = registry.get(playbook.playbook_code);

        if (playbookPackage?.uiLayout) {
          // Navigate to Playbook Surface
          router.push(`/workspaces/${newWorkspace.id}/playbook/${playbook.playbook_code}`);
        } else {
          // Navigate to regular workspace
          router.push(`/workspaces/${newWorkspace.id}`);
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        alert(t('workspaceCreateFailed') + ': ' + (errorData.detail || response.statusText));
      }
    } catch (err) {
      console.error('Failed to create workspace:', err);
      alert(t('workspaceCreateFailed') + ': ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setCreatingWorkspace(null);
    }
  };

  const filteredPlaybooks = useMemo(() => {
    if (!searchTerm) return playbooks;
    const lowerSearch = searchTerm.toLowerCase();
    return playbooks.filter(p =>
      (p.name && p.name.toLowerCase().includes(lowerSearch)) ||
      (p.description && p.description.toLowerCase().includes(lowerSearch))
    );
  }, [playbooks, searchTerm]);

  // Extract all unique tags from all playbooks
  const allTags = useMemo(() => {
    return Array.from(
      new Set(playbooks.flatMap(p => p.tags || []))
    ).sort();
  }, [playbooks]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Header />

      {/* Page Header - Single Row */}
      <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
          <div className="flex items-center justify-between gap-6">
            {/* Left: Title and Workflow */}
            <div className="flex items-center gap-6 flex-shrink-0">
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 whitespace-nowrap">
                {t('playbooksTitle')}
              </h1>
              {/* Workflow visualization */}
              <div className="hidden md:flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 bg-gradient-to-r from-blue-50 to-gray-50 dark:from-blue-900/20 dark:to-gray-800/20 rounded-lg px-3 py-2 border border-blue-100 dark:border-blue-800">
                <span className="text-base">🧠</span>
                <span>{t('playbookStepMindscape')}</span>
                <span className="text-gray-400 dark:text-gray-500">→</span>
                <span className="text-base">🔧</span>
                <span>{t('playbookStepTools')}</span>
                <span className="text-gray-400 dark:text-gray-500">→</span>
                <span className="text-base">🤖</span>
                <span>{t('playbookStepMembers')}</span>
              </div>
            </div>

            {/* Right: Search and Reload */}
            <div className="flex items-center gap-3 flex-1 max-w-xl">
              <input
                type="text"
                placeholder={t('searchPlaybooks')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
              <button
                onClick={() => {
                  setSelectedTags(prev => [...prev]);
                }}
                className="px-3 py-1.5 text-sm bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 whitespace-nowrap"
              >
                {t('reload')}
              </button>
            </div>
          </div>

          {error && (
            <div className="mt-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Three Column Layout */}
      <main className="w-full">
        <div className="grid grid-cols-12 gap-0">
          {/* Left Column: Filter Tags */}
          <div className="col-span-12 lg:col-span-2">
            <div className="bg-white dark:bg-gray-900 shadow h-[calc(100vh-8rem)] overflow-y-auto p-4 sticky top-0">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('filterTags')}</h3>

              {/* Tags Filter */}
              {allTags.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('tags')}</h4>
                  {allTags.map(tag => (
                    <label key={tag} className="flex items-center mb-2">
                      <input
                        type="checkbox"
                        checked={selectedTags.includes(tag)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedTags(prev => [...prev, tag]);
                          } else {
                            setSelectedTags(prev => prev.filter(t => t !== tag));
                          }
                        }}
                        className="mr-2"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">{tag}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Middle Column: Playbook Cards */}
          <div className="col-span-12 lg:col-span-7">
            <div className="h-[calc(100vh-8rem)] overflow-y-auto p-4">
              {loading ? (
                <p className="text-gray-600 dark:text-gray-400">{t('loading')}</p>
              ) : filteredPlaybooks.length === 0 ? (
                <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-12 text-center">
                  <p className="text-gray-600 dark:text-gray-400">{t('noPlaybooksFound')}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {filteredPlaybooks.map(playbook => (
                    <div
                      key={playbook.playbook_code}
                      className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 hover:shadow-lg transition-shadow flex flex-col cursor-pointer border border-gray-200 dark:border-gray-700"
                      onClick={() => router.push(`/playbooks/${playbook.playbook_code}`)}
                    >
                      {/* Top row: Icon, Scope/Template badge, System Playbook, Test badge, Favorite */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-3xl">{playbook.icon || '📋'}</span>
                          {playbook.scope && (
                            <span className={`text-xs px-2 py-1 rounded ${
                              playbook.scope === 'system'
                                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                                : playbook.scope === 'tenant'
                                ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                                : playbook.scope === 'profile'
                                ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                            }`}>
                              {playbook.scope === 'workspace' ? 'Instance' : 'Template'}
                            </span>
                          )}
                          {playbook.scope && playbook.scope !== 'workspace' && (
                            <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                              {playbook.scope.toUpperCase()}
                            </span>
                          )}
                          {playbook.kind === 'system_tool' && (
                            <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded">
                              {t('systemPlaybook')}
                            </span>
                          )}
                          {supportedTestPlaybooks.has(playbook.playbook_code) && (
                            <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded flex items-center gap-1">
                              🧪 {t('hasTest')}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            toggleFavorite(playbook.playbook_code, playbook.user_meta?.favorite || false);
                          }}
                          className="text-2xl hover:scale-110 transition-transform flex-shrink-0"
                        >
                          {playbook.user_meta?.favorite ? '⭐' : '☆'}
                        </button>
                      </div>

                      {/* Title */}
                      <h3 className="font-semibold text-lg mb-2 min-h-[3rem] text-gray-900 dark:text-gray-100">
                        {getPlaybookMetadata(playbook.playbook_code, 'name', locale as 'zh-TW' | 'en' | 'ja') || playbook.name}
                      </h3>

                      {/* Description */}
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2 flex-grow">
                        {getPlaybookMetadata(playbook.playbook_code, 'description', locale as 'zh-TW' | 'en' | 'ja') || playbook.description}
                      </p>

                      {/* Tags row */}
                      <div className="flex flex-wrap gap-2 mb-3 min-h-[1.5rem]">
                        {playbook.has_personal_variant && (
                          <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                            {t('hasPersonalVariant')}
                          </span>
                        )}
                        {(playbook.tags || []).slice(0, 2).map(tag => (
                          <span
                            key={tag}
                            className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>

                      {/* Onboarding task */}
                      {playbook.onboarding_task && (
                        <div className="text-xs text-blue-600 dark:text-blue-400 font-medium mb-2">
                          {t('coldStartTask')} {playbook.onboarding_task.replace('task', '')}
                        </div>
                      )}

                      {/* Bottom row: Usage count and action buttons */}
                      <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-100 dark:border-gray-700">
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          👁️ {playbook.user_meta?.use_count || 0} {t('times')}
                        </span>
                        <div className="flex items-center gap-2">
                          {playbook.scope && playbook.scope !== 'workspace' && (
                            <ForkPlaybookButton
                              playbookCode={playbook.playbook_code}
                              playbookName={playbook.name}
                            />
                          )}
                          <button
                            onClick={(e) => handleExecuteNow(e, playbook)}
                            disabled={creatingWorkspace === playbook.playbook_code}
                            className="px-3 py-1 text-xs bg-blue-600 dark:bg-blue-700 text-white rounded hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                          >
                            {creatingWorkspace === playbook.playbook_code ? t('creating') : t('executeNow')}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Playbook Discovery Chat */}
          <div className="col-span-12 lg:col-span-3">
            <div className="bg-white dark:bg-gray-900 shadow h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-0">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('findPlaybook')}</h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <PlaybookDiscoveryChat
                  onPlaybookSelect={(playbookCode) => {
                    router.push(`/playbooks/${playbookCode}`);
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
