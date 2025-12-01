'use client';

import React, { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import Header from '../../components/Header';
import { t, useLocale } from '../../lib/i18n';
import { getPlaybookMetadata } from '../../lib/i18n/locales/playbooks';

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
  user_meta: {
    favorite: boolean;
    use_count: number;
  };
  has_personal_variant?: boolean;
  default_variant_name?: string;
}

export default function PlaybooksPage() {
  const [locale] = useLocale();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [supportedTestPlaybooks, setSupportedTestPlaybooks] = useState<Set<string>>(new Set());

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
        const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';
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
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">
            {t('playbooksTitle')}
          </h1>

          {/* Workflow visualization with icons */}
          <div className="flex items-center gap-3 text-sm text-gray-600 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-4 border border-blue-100">
            <div className="flex items-center gap-2">
              <span className="text-2xl">🧠</span>
              <span className="font-medium">{t('playbookStepMindscape')}</span>
            </div>
            <span className="text-gray-400">→</span>
            <div className="flex items-center gap-2">
              <span className="text-2xl">🔧</span>
              <span className="font-medium">{t('playbookStepTools')}</span>
            </div>
            <span className="text-gray-400">→</span>
            <div className="flex items-center gap-2">
              <span className="text-2xl">🤖</span>
              <span className="font-medium">{t('playbookStepMembers')}</span>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {/* Search and Reindex */}
        <div className="flex gap-4 mb-6">
          <input
            type="text"
            placeholder={t('searchPlaybooks')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 px-4 py-2 border rounded-md"
          />
          <button
            onClick={() => {
              // Force reload by creating new array reference
              setSelectedTags(prev => [...prev]);
            }}
            className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
          >
            {t('reload')}
          </button>
        </div>

        <div className="flex gap-6">
          {/* Sidebar Filters */}
          <div className="w-64 flex-shrink-0">
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-4">{t('filterTags')}</h3>

              {/* Tags Filter */}
              {allTags.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">{t('tags')}</h4>
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
                      <span className="text-sm">{tag}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Playbook Cards */}
          <div className="flex-1">
            {loading ? (
              <p className="text-gray-600">{t('loading')}</p>
            ) : filteredPlaybooks.length === 0 ? (
              <div className="bg-white shadow rounded-lg p-12 text-center">
                <p className="text-gray-600">{t('noPlaybooksFound')}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredPlaybooks.map(playbook => (
                  <div
                    key={playbook.playbook_code}
                    className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow relative"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <span className="text-3xl">{playbook.icon || '📋'}</span>
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          toggleFavorite(playbook.playbook_code, playbook.user_meta?.favorite || false);
                        }}
                        className="text-2xl hover:scale-110 transition-transform"
                      >
                        {playbook.user_meta?.favorite ? '⭐' : '☆'}
                      </button>
                    </div>

                    <h3 className="font-semibold text-lg mb-2">
                      {getPlaybookMetadata(playbook.playbook_code, 'name', locale as 'zh-TW' | 'en') || playbook.name}
                    </h3>
                    <p className="text-sm text-gray-600 mb-4 line-clamp-2">
                      {getPlaybookMetadata(playbook.playbook_code, 'description', locale as 'zh-TW' | 'en') || playbook.description}
                    </p>

                    <div className="flex flex-wrap gap-2 mb-3">
                      <span className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded">
                        系統 Playbook
                      </span>
                      {playbook.has_personal_variant && (
                        <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
                          已有個人版本
                        </span>
                      )}
                      {supportedTestPlaybooks.has(playbook.playbook_code) && (
                        <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded flex items-center gap-1">
                          🧪 有測試
                        </span>
                      )}
                      {(playbook.tags || []).slice(0, 2).map(tag => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-1 bg-purple-100 text-purple-700 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    {playbook.onboarding_task && (
                      <div className="text-xs text-blue-600 font-medium mb-2">
                        {t('coldStartTask')} {playbook.onboarding_task.replace('task', '')}
                      </div>
                    )}

                    <div className="flex items-center justify-between mt-4">
                      <span className="text-xs text-gray-500">
                        👁️ {playbook.user_meta?.use_count || 0} {t('times')}
                      </span>
                      <div className="flex gap-2">
                        <Link
                          href={`/playbooks/${playbook.playbook_code}`}
                          className="px-3 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                        >
                          查看詳情
                        </Link>
                        <Link
                          href={`/playbooks/${playbook.playbook_code}?execute=true`}
                          className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                          立即執行
                        </Link>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
