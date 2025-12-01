'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
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

export default function PlaybookDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const playbookCode = Array.isArray(params?.code) ? params.code[0] : (params?.code as string);
  const onboardingTask = searchParams?.get('onboarding');
  const [locale] = useLocale();

  const [playbook, setPlaybook] = useState<Playbook | null>(null);
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
  const [activeTab, setActiveTab] = useState<'info' | 'sop' | 'suggestions' | 'history'>('info');
  const [selectedVersion, setSelectedVersion] = useState<'system' | 'personal'>('system');

  useEffect(() => {
    if (playbookCode) {
      loadPlaybook();
      loadVariants();
    }
  }, [playbookCode, locale]);

  // Poll for execution status updates every 5 seconds
  useEffect(() => {
    if (!playbookCode) return;

    const interval = setInterval(() => {
      // Silently reload execution status without showing loading state
      loadPlaybookStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, [playbookCode]);

  const loadPlaybook = async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
      }
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';

      // Use locale from useLocale hook to determine target_language
      // This ensures we get the actual user-selected language
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

      // Set default version selection based on version_info
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
    // Silent update for polling - only update execution status
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
        // Only update execution status and version info, preserve other state
        setPlaybook(prev => prev ? {
          ...prev,
          execution_status: data.execution_status,
          version_info: data.version_info
        } : data);
      }
    } catch (err) {
      // Silently fail for polling updates
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
        // Success - alert will be shown by caller if needed
      } else {
        throw new Error('Failed to save');
      }
    } catch (err) {
      console.error('Failed to save user notes:', err);
      alert('儲存失敗');
      throw err;
    }
  };

  const loadAssociatedIntents = async () => {
    // Placeholder - will be implemented later
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
      }
    } catch (err) {
      console.error('Failed to load variants:', err);
    }
  };

  const handleCopySystemVersion = async (variantName: string, variantDescription: string) => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/variants/copy?profile_id=default-user&variant_name=${encodeURIComponent(variantName || '我的版本')}&variant_description=${encodeURIComponent(variantDescription || '')}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } }
      );
      if (response.ok) {
        const variant = await response.json();
        setShowCopyModal(false);
        await loadPlaybook(); // Reload to get updated version_info
        await loadVariants();
        setSelectedVersion('personal');
        alert(`已建立個人版本「${variant.variant_name}」，後續執行將使用此版本`);
      } else {
        throw new Error('Failed to create variant');
      }
    } catch (err: any) {
      console.error('Failed to copy system version:', err);
      alert('建立個人版本失敗：' + err.message);
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
      alert('獲取優化建議失敗：' + err.message);
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

    // Get variant_id if using personal version
    let variantId = null;
    if (selectedVersion === 'personal' && playbook.version_info?.default_variant?.id) {
      variantId = playbook.version_info.default_variant.id;
    }

    setIsExecuting(true);

    try {
      // Create or find workspace for this playbook
      const playbookName = playbook.metadata.name;
      const targetLanguage = locale === 'en' ? 'en' : 'zh-TW';

      // Create new workspace with playbook configuration
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

      // Build redirect URL with auto-execute parameter
      const redirectUrl = new URL(`/workspaces/${workspaceId}`, window.location.origin);
      redirectUrl.searchParams.set('auto_execute_playbook', 'true');
      if (variantId) {
        redirectUrl.searchParams.set('variant_id', variantId);
      }

      // Redirect to workspace page
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
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-gray-600">{t('loading')}</p>
          </div>
        </main>
      </div>
    );
  }

  if (error || !playbook) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">{error || 'Playbook not found'}</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Link
          href="/playbooks"
          className="text-blue-600 hover:text-blue-800 mb-4 inline-block"
        >
          ← {t('backToList')}
        </Link>

        {/* Top Section: Playbook Info + Version Selector */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <PlaybookInfo
            playbook={playbook}
            isFavorite={isFavorite}
            onToggleFavorite={toggleFavorite}
            profileId="default-user"
          />
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

        <PlaybookTabs
          activeTab={activeTab}
          onTabChange={setActiveTab}
          selectedVersion={selectedVersion}
          playbook={playbook}
          onCopyClick={() => setShowCopyModal(true)}
          onLLMClick={() => setShowLLMDrawer(true)}
        />

        {/* Execute Button */}
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <button
            onClick={handleExecutePlaybook}
            disabled={isExecuting}
            className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-lg font-medium"
          >
            {isExecuting ? '執行中...' : selectedVersion === 'personal' && playbook.version_info?.default_variant
              ? `在 Workspace 中執行「${playbook.version_info.default_variant.variant_name}」`
              : '在 Workspace 中執行（系統標準版）'}
          </button>
        </div>

        {/* Modals and Drawers */}
        <CopyVariantModal
          isOpen={showCopyModal}
          onClose={() => setShowCopyModal(false)}
          onConfirm={handleCopySystemVersion}
          playbookName={(() => {
            const localeStr = Array.isArray(locale) ? locale[0] : (typeof locale === 'string' ? locale : 'en');
            const name = getPlaybookMetadata(playbookCode, 'name', localeStr as 'zh-TW' | 'en') || playbook.metadata.name;
            return typeof name === 'string' ? name : String(name || '');
          })()}
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
            <div className="bg-white rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">💡 Playbook 優化建議</h2>
                <button
                  onClick={() => {
                    setShowOptimizeModal(false);
                    setOptimizationSuggestions([]);
                  }}
                  className="text-gray-400 hover:text-gray-600 text-2xl"
                >
                  ×
                </button>
              </div>

              {optimizationLoading ? (
                <div className="text-center py-8">
                  <p className="text-gray-600">正在分析使用模式並生成建議...</p>
                </div>
              ) : optimizationSuggestions.length > 0 ? (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600 mb-4">
                    根據您的使用模式，我們為您生成了以下優化建議：
                  </p>
                  {optimizationSuggestions.map((suggestion, index) => (
                    <div
                      key={index}
                      className="p-4 border border-gray-200 rounded-lg hover:border-blue-300 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-medium text-gray-900 mb-1">{suggestion.title}</h3>
                          <p className="text-sm text-gray-600 mb-2">{suggestion.description}</p>
                          <p className="text-xs text-gray-500">{suggestion.rationale}</p>
                          {suggestion.step_number && (
                            <span className="inline-block mt-2 px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                              步驟 {suggestion.step_number}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={async () => {
                            // Create variant from this suggestion
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
                                alert('變體已創建！');
                                loadVariants();
                                setShowOptimizeModal(false);
                              } else {
                                throw new Error('Failed to create variant');
                              }
                            } catch (err: any) {
                              alert('創建變體失敗：' + err.message);
                            }
                          }}
                          className="ml-4 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                          應用
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-600">暫無優化建議。繼續使用 Playbook 以獲得更多數據。</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Notes Modal */}
        {showNotesModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">{t('myNotes')}</h2>
                <button
                  onClick={() => setShowNotesModal(false)}
                  className="text-gray-400 hover:text-gray-600 text-2xl"
                >
                  ×
                </button>
              </div>
              <textarea
                value={userNotes}
                onChange={(e) => setUserNotes(e.target.value)}
                className="w-full px-4 py-2 border rounded-md mb-4"
                rows={8}
                placeholder={t('writeYourNotesHere')}
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowNotesModal(false)}
                  className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  onClick={async () => {
                    await saveUserNotes();
                    setShowNotesModal(false);
                  }}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                >
                  {t('saveNotes')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Chat Interface (shown when execution is active) */}
        {executionId && (
          <div className="bg-white shadow rounded-lg p-6 mb-6">
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
              <p className="text-xs text-gray-500 text-center mt-2">
                {t('willReturnAfterCompletion')}
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
