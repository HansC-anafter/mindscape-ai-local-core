'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../components/Header';
import PlaybookChat from '../../../components/PlaybookChat';
import { t, useLocale } from '../../../lib/i18n';
import { getPlaybookMetadata } from '../../../lib/i18n/locales/playbooks';
import PlaybookInfo from '../../../components/playbook/PlaybookInfo';
import VersionSelector from '../../../components/playbook/VersionSelector';
import PlaybookTabs from '../../../components/playbook/PlaybookTabs';
import CopyVariantModal from '../../../components/playbook/CopyVariantModal';
import LLMDrawer from '../../../components/playbook/LLMDrawer';
import PlaybookDiscoveryChat from '../../../components/playbook/PlaybookDiscoveryChat';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Playbook {
  metadata: {
    playbook_code: string;
    version: string;
    locale: string;
    name: string;
    description: string;
    tags: string[];
    entry_agent_type?: string;
    onboarding_task?: string;
    icon?: string;
    required_tools: string[];
    scope?: any;
    owner?: any;
  };
  sop_content: string;
  user_notes?: string;
  user_meta: {
    favorite?: boolean;
    use_count?: number;
  };
  associated_intents: Array<{
    intent_id: string;
    title: string;
    status?: string;
    priority?: string;
  }>;
  execution_status?: {
    active_executions: Array<{
      execution_id: string;
      status: string;
      started_at?: string;
    }>;
    recent_executions: Array<{
      execution_id: string;
      status: string;
      started_at?: string;
      completed_at?: string;
    }>;
  };
  version_info?: {
    has_personal_variant: boolean;
    default_variant: any;
    system_version: string;
  };
}

interface PlaybookListItem {
  playbook_code: string;
  name: string;
  description: string;
  icon?: string;
}

export default function PlaybookDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const playbookCode = Array.isArray(params?.code) ? params.code[0] : (params?.code as string);
  const onboardingTask = searchParams?.get('onboarding');
  const [locale] = useLocale();

  const [playbook, setPlaybook] = useState<Playbook | null>(null);
  const [playbookList, setPlaybookList] = useState<PlaybookListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionComplete, setExecutionComplete] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [initialMessage, setInitialMessage] = useState<string>('');
  const [userNotes, setUserNotes] = useState('');
  const [isFavorite, setIsFavorite] = useState(false);
  const [showNotesModal, setShowNotesModal] = useState(false);
  const [showOptimizeModal, setShowOptimizeModal] = useState(false);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [showLLMDrawer, setShowLLMDrawer] = useState(false);
  const [optimizationSuggestions, setOptimizationSuggestions] = useState<any[]>([]);
  const [optimizationLoading, setOptimizationLoading] = useState(false);
  const [variants, setVariants] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'info' | 'sop' | 'suggestions' | 'history'>('sop');
  const [selectedVersion, setSelectedVersion] = useState<'system' | 'personal'>('system');

  // Prevent auto-scroll to top on route change
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.history.scrollRestoration = 'manual';

      // Prevent scroll on route change
      const handleRouteChange = () => {
        window.scrollTo(0, window.scrollY);
      };

      // Store current scroll position before route change
      const scrollY = window.scrollY;

      // Restore scroll position after a short delay
      setTimeout(() => {
        if (window.scrollY !== scrollY) {
          window.scrollTo(0, scrollY);
        }
      }, 0);
    }
  }, [playbookCode]);

  useEffect(() => {
    if (playbookCode) {
      loadPlaybook();
      loadVariants();
      loadPlaybookList();
    }
  }, [playbookCode, locale]);

  // Poll for execution status updates every 5 seconds
  useEffect(() => {
    if (!playbookCode) return;

    const interval = setInterval(() => {
      loadPlaybookStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, [playbookCode]);

  const loadPlaybookList = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks?target_language=${targetLanguage}&profile_id=default-user`,
        { headers: { 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const data = await response.json();
        setPlaybookList(data.map((p: any) => ({
          playbook_code: p.playbook_code,
          name: getPlaybookMetadata(p.playbook_code, 'name', targetLanguage as 'zh-TW' | 'en') || p.name,
          description: getPlaybookMetadata(p.playbook_code, 'description', targetLanguage as 'zh-TW' | 'en') || p.description,
          icon: p.icon
        })));
      }
    } catch (err) {
      console.debug('Failed to load playbook list:', err);
    }
  };

  const loadPlaybook = async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
      }
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';

      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}?profile_id=default-user&target_language=${targetLanguage}`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to load playbook');
      }

      const data = await response.json();
      setPlaybook(data);
      setUserNotes(data.user_notes || '');
      setIsFavorite(data.user_meta?.favorite || false);

      if (data.version_info?.has_personal_variant && data.version_info?.default_variant) {
        setSelectedVersion('personal');
      } else {
        setSelectedVersion('system');
      }
    } catch (err: any) {
      if (showLoading) {
        setError(err.message || 'Failed to load playbook');
      }
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  };

  const loadPlaybookStatus = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';

      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}?profile_id=default-user&target_language=${targetLanguage}`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setPlaybook(prev => prev ? {
          ...prev,
          execution_status: data.execution_status,
          version_info: data.version_info
        } : data);
      }
    } catch (err) {
      console.debug('Failed to update execution status:', err);
    }
  };

  const toggleFavorite = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      await fetch(`${apiUrl}/api/v1/playbooks/${playbookCode}/meta?profile_id=default-user&favorite=${!isFavorite}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      });
      setIsFavorite(!isFavorite);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  };

  const saveUserNotes = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/playbooks/${playbookCode}/meta?profile_id=default-user&user_notes=${encodeURIComponent(userNotes)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        // Success
      } else {
        throw new Error('Failed to save');
      }
    } catch (err) {
      console.error('Failed to save user notes:', err);
      alert(t('playbookSaveFailed'));
      throw err;
    }
  };

  const loadVariants = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/variants?profile_id=default-user`,
        { headers: { 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const data = await response.json();
        setVariants(data);
      } else if (response.status === 404) {
        setVariants([]);
      } else {
        setVariants([]);
        console.debug(`Variants endpoint returned ${response.status} for ${playbookCode}`);
      }
    } catch (err) {
      console.debug('Variants endpoint not available:', err);
      setVariants([]);
    }
  };

  const handleCopySystemVersion = async (variantName: string, variantDescription: string) => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/copy?profile_id=default-user&variant_name=${encodeURIComponent(variantName || t('playbookMyVariantDefault'))}&variant_description=${encodeURIComponent(variantDescription || '')}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const variant = await response.json();
        setShowCopyModal(false);
        await loadPlaybook();
        await loadVariants();
        setSelectedVersion('personal');
        alert(t('playbookVariantCreated', { name: variant.variant_name }));
      } else {
        throw new Error('Failed to create variant');
      }
    } catch (err: any) {
      console.error('Failed to copy system version:', err);
      alert(t('playbookCreateVariantFailedError', { error: err.message }));
    }
  };

  const handleOptimize = async () => {
    try {
      setOptimizationLoading(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/optimize?profile_id=default-user`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      if (response.ok) {
        const data = await response.json();
        setOptimizationSuggestions(data.suggestions || []);
      } else {
        throw new Error('Failed to get optimization suggestions');
      }
    } catch (err: any) {
      console.error('Failed to optimize:', err);
      alert(t('playbookGetSuggestionsFailed', { error: err.message }));
    } finally {
      setOptimizationLoading(false);
    }
  };

  useEffect(() => {
    if (playbookCode && showOptimizeModal) {
      handleOptimize();
      loadVariants();
    }
  }, [playbookCode, showOptimizeModal]);

  const handleExecutePlaybook = async () => {
    if (!playbook) return;

    const apiUrl = API_URL.startsWith('http') ? API_URL : '';
    const profileId = 'default-user';

    let variantId = null;
    if (selectedVersion === 'personal' && playbook.version_info?.default_variant?.id) {
      variantId = playbook.version_info.default_variant.id;
    }

    setIsExecuting(true);

    try {
      const playbookName = playbook.metadata.name;
      const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';

      const createResponse = await fetch(
        `${apiUrl}/api/v1/workspaces?owner_user_id=${profileId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: `${playbookName} Workspace`,
            description: `Workspace for executing ${playbookName}`,
            default_playbook_id: playbookCode,
            default_locale: targetLanguage
          })
        }
      );

      if (!createResponse.ok) {
        throw new Error('Failed to create workspace');
      }

      const workspace = await createResponse.json();
      const workspaceId = workspace.id;

      const redirectUrl = new URL(`/workspaces/${workspaceId}`, window.location.origin);
      redirectUrl.searchParams.set('auto_execute_playbook', 'true');
      if (variantId) {
        redirectUrl.searchParams.set('variant_id', variantId);
      }

      window.location.href = redirectUrl.toString();
    } catch (err: any) {
      console.error('Failed to create workspace and execute playbook:', err);
      alert(`執行失敗：${err.message}`);
      setIsExecuting(false);
    }
  };

  const handleChatComplete = async (structuredOutput: any) => {
    const apiUrl = API_URL.startsWith('http') ? API_URL : '';
    const profileId = 'default-user';

    console.log('Playbook execution completed:', structuredOutput);
    setExecutionComplete(true);

    if (onboardingTask && executionId) {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/mindscape/playbook/webhook?execution_id=${executionId}&playbook_code=${playbookCode}&profile_id=${profileId}`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(structuredOutput)
          }
        );

        if (response.ok) {
          const result = await response.json();
          console.log('Webhook result:', result);

          setTimeout(() => {
            window.location.href = '/mindscape';
          }, 1500);
        } else {
          throw new Error('Webhook failed');
        }
      } catch (err) {
        console.error('Failed to handle onboarding completion:', err);
      }
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <Header />
        <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-gray-600 dark:text-gray-400">{t('loading')}</p>
          </div>
        </main>
      </div>
    );
  }

  if (error || !playbook) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <Header />
        <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-300">{error || 'Playbook not found'}</p>
          </div>
        </main>
      </div>
    );
  }

  const playbookName = getPlaybookMetadata(playbookCode, 'name', locale as 'zh-TW' | 'en') || playbook.metadata.name;
  const playbookDescription = getPlaybookMetadata(playbookCode, 'description', locale as 'zh-TW' | 'en') || playbook.metadata.description;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950" style={{ scrollBehavior: 'auto' }}>
      <Header />

      {/* Version Selector and Execute Button in Header */}
      <div className="bg-orange-50 dark:bg-orange-900/20 border-b border-orange-200 dark:border-orange-800 sticky top-12 z-40">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
          <div className="flex items-center gap-4">
            {/* Left: Breadcrumb */}
            <div className="flex-shrink-0 w-48">
              <Link
                href="/playbooks"
                className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span>{t('backToList')}</span>
              </Link>
            </div>

            {/* Center: Version Selector */}
            <div className="flex-1 flex justify-center">
              <VersionSelector
                hasPersonalVariant={playbook.version_info?.has_personal_variant || false}
                defaultVariant={playbook.version_info?.default_variant}
                systemVersion={playbook.version_info?.system_version || playbook.metadata.version}
                selectedVersion={selectedVersion}
                onVersionChange={setSelectedVersion}
                onCopyClick={() => setShowCopyModal(true)}
                onLLMClick={() => setShowLLMDrawer(true)}
                activeExecutionsCount={playbook.execution_status?.active_executions?.length || 0}
              />
            </div>

            {/* Right: Execute Button */}
            <div className="flex-shrink-0 w-48 flex justify-end">
              <button
                onClick={handleExecutePlaybook}
                disabled={isExecuting}
                className="px-6 py-2.5 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-sm font-medium whitespace-nowrap"
              >
                {isExecuting ? t('executing') : selectedVersion === 'personal' && playbook.version_info?.default_variant
                  ? t('executingVariant', { name: playbook.version_info.default_variant.variant_name })
                  : t('executingInWorkspace')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <main className="w-full">
        {/* Three Column Layout */}
        <div className="grid grid-cols-12 gap-0">
          {/* Left Column: Playbook List */}
          <div className="col-span-12 lg:col-span-2">
            <div className="bg-white dark:bg-gray-900 shadow h-[calc(100vh-7rem)] overflow-y-auto p-4 sticky top-[7rem]">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('playbookList')}</h3>
              <div className="space-y-2">
                {playbookList.map((pb) => (
                  <Link
                    key={pb.playbook_code}
                    href={`/playbooks/${pb.playbook_code}`}
                    scroll={false}
                    className={`block p-3 rounded-lg transition-colors ${
                      pb.playbook_code === playbookCode
                        ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800 border border-transparent'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {pb.icon && <span className="text-lg flex-shrink-0">{pb.icon}</span>}
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium truncate ${
                          pb.playbook_code === playbookCode ? 'text-blue-900 dark:text-blue-300' : 'text-gray-900 dark:text-gray-100'
                        }`}>
                          {pb.name}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2 mt-1">
                          {pb.description}
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          {/* Middle Column: Main Content (SOP as default) */}
          <div className="col-span-12 lg:col-span-7">
            <div className="h-[calc(100vh-7rem)] overflow-y-auto">
              {/* Playbook Header */}
              <div className="bg-white dark:bg-gray-800 shadow p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{playbookName}</h1>
                      {playbook.metadata.icon && <span className="text-3xl">{playbook.metadata.icon}</span>}
                      <button
                        onClick={toggleFavorite}
                        className="text-2xl hover:scale-110 transition-transform flex-shrink-0"
                      >
                        {isFavorite ? '⭐' : '☆'}
                      </button>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{playbookDescription}</p>
                    <div className="flex flex-wrap gap-2">
                      {playbook.metadata.tags?.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Tabs with SOP as default */}
              <PlaybookTabs
                activeTab={activeTab}
                onTabChange={setActiveTab}
                selectedVersion={selectedVersion}
                playbook={playbook}
                onCopyClick={() => setShowCopyModal(true)}
                onLLMClick={() => setShowLLMDrawer(true)}
              />
            </div>
          </div>

          {/* Right Column: LLM Component for Finding Playbooks */}
          <div className="col-span-12 lg:col-span-3">
            <div className="bg-white dark:bg-gray-900 shadow h-[calc(100vh-7rem)] flex flex-col p-4 sticky top-[7rem]">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('findPlaybook')}</h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <PlaybookDiscoveryChat
                  onPlaybookSelect={(playbookCode) => {
                    router.push(`/playbooks/${playbookCode}`, { scroll: false });
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Modals and Drawers */}
        <CopyVariantModal
          isOpen={showCopyModal}
          onClose={() => setShowCopyModal(false)}
          onConfirm={handleCopySystemVersion}
          playbookName={typeof playbookName === 'string' ? playbookName : String(playbookName || '')}
        />

        <LLMDrawer
          isOpen={showLLMDrawer}
          onClose={() => setShowLLMDrawer(false)}
          playbookCode={playbookCode}
          systemSOP={playbook.sop_content}
          onVariantCreated={async () => {
            await loadPlaybook();
            await loadVariants();
            setSelectedVersion('personal');
          }}
        />

        {/* Optimization Modal */}
        {showOptimizeModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('playbookOptimizationSuggestions')}</h2>
                <button
                  onClick={() => {
                    setShowOptimizeModal(false);
                    setOptimizationSuggestions([]);
                  }}
                  className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-2xl"
                >
                  ×
                </button>
              </div>

              {optimizationLoading ? (
                <div className="text-center py-8">
                  <p className="text-gray-600 dark:text-gray-400">{t('analyzingPatterns')}</p>
                </div>
              ) : optimizationSuggestions.length > 0 ? (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    {t('basedOnUsagePattern')}
                  </p>
                  {optimizationSuggestions.map((suggestion, index) => (
                    <div
                      key={index}
                      className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-300 dark:hover:border-blue-600 transition-colors bg-white dark:bg-gray-800"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-1">{suggestion.title}</h3>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{suggestion.description}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{suggestion.rationale}</p>
                          {suggestion.step_number && (
                            <span className="inline-block mt-2 px-2 py-1 text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 rounded">
                              {t('step')} {suggestion.step_number}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={async () => {
                            try {
                              const apiUrl = API_URL.startsWith('http') ? API_URL : '';
                              const response = await fetch(
                                `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/from-suggestions?profile_id=default-user`,
                                {
                                  method: 'POST',
                                  headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({
                                    variant_name: `${suggestion.title} - ${new Date().toLocaleDateString()}`,
                                    selected_suggestions: [suggestion]
                                  })
                                }
                              );
                              if (response.ok) {
                                alert(t('playbookVariantCreatedSuccess'));
                                loadVariants();
                                setShowOptimizeModal(false);
                              } else {
                                throw new Error('Failed to create variant');
                              }
                            } catch (err: any) {
                              alert(t('playbookCreateVariantFailedError', { error: err.message }));
                            }
                          }}
                          className="ml-4 px-3 py-1 text-sm bg-blue-600 dark:bg-blue-700 text-white rounded hover:bg-blue-700 dark:hover:bg-blue-600"
                        >
                          {t('apply')}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-600 dark:text-gray-400">{t('noOptimizationSuggestions')}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Notes Modal */}
        {showNotesModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('myNotes')}</h2>
                <button
                  onClick={() => setShowNotesModal(false)}
                  className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-2xl"
                >
                  ×
                </button>
              </div>
              <textarea
                value={userNotes}
                onChange={(e) => setUserNotes(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md mb-4 focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                rows={8}
                placeholder={t('writeYourNotesHere')}
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowNotesModal(false)}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
                >
                  {t('cancel')}
                </button>
                <button
                  onClick={async () => {
                    await saveUserNotes();
                    setShowNotesModal(false);
                  }}
                  className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
                >
                  {t('saveNotes')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Chat Interface (shown when execution is active) */}
        {executionId && (
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 mb-6">
            <PlaybookChat
              executionId={executionId}
              playbookCode={playbookCode}
              profileId="default-user"
              initialMessage={initialMessage}
              isComplete={executionComplete}
              onComplete={handleChatComplete}
              apiUrl={API_URL.startsWith('http') ? API_URL : ''}
            />
            {onboardingTask && !executionComplete && (
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
                {t('willReturnAfterCompletion')}
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
