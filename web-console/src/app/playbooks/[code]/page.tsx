'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { t, useLocale } from '../../../lib/i18n';
import { PlaybookDetailModals } from './PlaybookDetailModals';
import { PlaybookDetailView, PlaybookErrorView, PlaybookLoadingView } from './PlaybookDetailView';
import {
  API_URL,
  copySystemVersion,
  createPlaybookWorkspace,
  createVariantFromSuggestion,
  fetchPlaybookDetail,
  fetchPlaybookList,
  fetchPlaybookStatus,
  fetchPlaybookVariants,
  requestOptimizationSuggestions,
  resolveApiBaseUrl,
  sendOnboardingWebhook,
  targetLanguageForLocale,
  updatePlaybookFavorite,
  updatePlaybookNotes,
} from './playbookDetailApi';
import {
  getBrowserLocalStorage,
  readRecentPlaybookViews,
  recordRecentPlaybookView,
  selectRecentPlaybooks,
} from './recentPlaybooks';
import type {
  OptimizationSuggestion,
  Playbook,
  PlaybookListItem,
  PlaybookTab,
  VersionSelection,
} from './playbookDetailTypes';

export default function PlaybookDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const playbookCode = Array.isArray(params?.code) ? params?.code[0] : (params?.code as string);
  const onboardingTask = searchParams?.get('onboarding' as any);
  const workspaceId = searchParams?.get('workspace' as any);
  const [locale] = useLocale();

  const [playbook, setPlaybook] = useState<Playbook | null>(null);
  const [playbookList, setPlaybookList] = useState<PlaybookListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionComplete, setExecutionComplete] = useState(false);
  const [executionId] = useState<string | null>(null);
  const [initialMessage] = useState<string>('');
  const [userNotes, setUserNotes] = useState('');
  const [isFavorite, setIsFavorite] = useState(false);
  const [showNotesModal, setShowNotesModal] = useState(false);
  const [showOptimizeModal, setShowOptimizeModal] = useState(false);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [showLLMDrawer, setShowLLMDrawer] = useState(false);
  const [optimizationSuggestions, setOptimizationSuggestions] = useState<OptimizationSuggestion[]>([]);
  const [optimizationLoading, setOptimizationLoading] = useState(false);
  const [, setVariants] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<PlaybookTab>('sop');
  const [selectedVersion, setSelectedVersion] = useState<VersionSelection>('system');
  const [recentPlaybooks, setRecentPlaybooks] = useState<PlaybookListItem[]>([]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.history.scrollRestoration = 'manual';
      const scrollY = window.scrollY;

      setTimeout(() => {
        if (window.scrollY !== scrollY) {
          window.scrollTo(0, scrollY);
        }
      }, 0);
    }
  }, [playbookCode]);

  useEffect(() => {
    const storage = getBrowserLocalStorage();
    if (!storage) {
      return;
    }

    try {
      setRecentPlaybooks(selectRecentPlaybooks(readRecentPlaybookViews(storage), playbookCode));
    } catch (err) {
      console.debug('Failed to load recent playbooks from localStorage:', err);
    }
  }, [playbookCode]);

  const loadPlaybookList = useCallback(async () => {
    try {
      const list = await fetchPlaybookList(locale);
      if (list) {
        setPlaybookList(list);
      }
    } catch (err) {
      console.debug('Failed to load playbook list:', err);
    }
  }, [locale]);

  const loadPlaybook = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) {
        setLoading(true);
        setError(null);
      }

      const data = await fetchPlaybookDetail(playbookCode, locale);

      setPlaybook(data);
      setUserNotes(data.user_notes || '');
      setIsFavorite(data.user_meta?.favorite || false);
      setSelectedVersion(data.version_info?.has_personal_variant && data.version_info?.default_variant ? 'personal' : 'system');

      const storage = getBrowserLocalStorage();
      if (storage && data.metadata) {
        try {
          setRecentPlaybooks(recordRecentPlaybookView(storage, playbookCode, {
            name: data.metadata.name,
            description: data.metadata.description,
            icon: data.metadata.icon,
          }));
        } catch (err) {
          console.debug('Failed to save recent playbook to localStorage:', err);
        }
      }
    } catch (err: any) {
      console.error('[PlaybookPage] Error loading playbook:', err);
      if (showLoading) {
        let errorMessage = 'Failed to load playbook';
        if (err.name === 'AbortError' || err.name === 'TimeoutError') {
          errorMessage = 'Request timeout. Please check your network connection.';
        } else if (err.message) {
          errorMessage = err.message;
        }
        setError(errorMessage);
        setLoading(false);
      }
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }, [locale, playbookCode]);

  const loadPlaybookStatus = useCallback(async () => {
    try {
      const data = await fetchPlaybookStatus(playbookCode, locale);
      if (!data) {
        return;
      }

      setPlaybook((prev) => {
        if (!prev) {
          return data;
        }
        return {
          ...prev,
          execution_status: data.execution_status,
          version_info: data.version_info,
        };
      });
    } catch (err) {
      console.debug('Failed to update execution status:', err);
    }
  }, [locale, playbookCode]);

  const toggleFavorite = async () => {
    try {
      await updatePlaybookFavorite(playbookCode, !isFavorite);
      setIsFavorite(!isFavorite);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    }
  };

  const saveUserNotes = async () => {
    try {
      const response = await updatePlaybookNotes(playbookCode, userNotes);
      if (!response.ok) {
        throw new Error('Failed to save');
      }
    } catch (err) {
      console.error('Failed to save user notes:', err);
      alert(t('playbookSaveFailed' as any));
      throw err;
    }
  };

  const loadVariants = useCallback(async () => {
    try {
      const result = await fetchPlaybookVariants(playbookCode);
      setVariants(result.variants);
      if (result.status !== 200 && result.status !== 404) {
        console.debug(`Variants endpoint returned ${result.status} for ${playbookCode}`);
      }
    } catch (err) {
      console.debug('Variants endpoint not available:', err);
      setVariants([]);
    }
  }, [playbookCode]);

  const handleCopySystemVersion = async (variantName: string, variantDescription: string) => {
    try {
      const variant = await copySystemVersion(
        playbookCode,
        variantName || t('playbookMyVariantDefault' as any),
        variantDescription || ''
      );
      setShowCopyModal(false);
      await loadPlaybook();
      await loadVariants();
      setSelectedVersion('personal');
      alert(t('playbookVariantCreated', { name: variant.variant_name }));
    } catch (err: any) {
      console.error('Failed to copy system version:', err);
      alert(t('playbookCreateVariantFailedError', { error: err.message }));
    }
  };

  const handleOptimize = useCallback(async () => {
    try {
      setOptimizationLoading(true);
      setOptimizationSuggestions(await requestOptimizationSuggestions(playbookCode));
    } catch (err: any) {
      console.error('Failed to optimize:', err);
      alert(t('playbookGetSuggestionsFailed', { error: err.message }));
    } finally {
      setOptimizationLoading(false);
    }
  }, [playbookCode]);

  useEffect(() => {
    if (playbookCode) {
      loadPlaybook();
      loadVariants();
      loadPlaybookList();
    }
  }, [playbookCode, loadPlaybook, loadVariants, loadPlaybookList]);

  useEffect(() => {
    if (!playbookCode || loading) return;

    const interval = setInterval(() => {
      loadPlaybookStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, [playbookCode, loading, loadPlaybookStatus]);

  useEffect(() => {
    if (playbookCode && showOptimizeModal) {
      handleOptimize();
      loadVariants();
    }
  }, [playbookCode, showOptimizeModal, handleOptimize, loadVariants]);

  const handleExecutePlaybook = async () => {
    if (!playbook) return;

    let variantId = null;
    if (selectedVersion === 'personal' && playbook.version_info?.default_variant?.id) {
      variantId = playbook.version_info.default_variant.id;
    }

    setIsExecuting(true);

    try {
      const playbookName = playbook.metadata.name;
      const workspace = await createPlaybookWorkspace(
        playbookCode,
        playbookName,
        targetLanguageForLocale(locale)
      );
      const redirectUrl = new URL(`/workspaces/${workspace.id}`, window.location.origin);
      redirectUrl.searchParams.set('auto_execute_playbook', 'true');
      if (variantId) {
        redirectUrl.searchParams.set('variant_id', variantId);
      }

      window.location.href = redirectUrl.toString();
    } catch (err: any) {
      console.error('Failed to create workspace and execute playbook:', err);
      alert(t('executionFailedWithError', { error: err.message }));
      setIsExecuting(false);
    }
  };

  const handleChatComplete = async (structuredOutput: any) => {
    console.log('Playbook execution completed:', structuredOutput);
    setExecutionComplete(true);

    if (onboardingTask && executionId) {
      try {
        const response = await sendOnboardingWebhook(executionId, playbookCode, structuredOutput);

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

  const handleApplySuggestion = async (suggestion: OptimizationSuggestion) => {
    try {
      await createVariantFromSuggestion(playbookCode, suggestion);
      alert(t('playbookVariantCreatedSuccess' as any));
      loadVariants();
      setShowOptimizeModal(false);
    } catch (err: any) {
      alert(t('playbookCreateVariantFailedError', { error: err.message }));
    }
  };

  const closeOptimizeModal = () => {
    setShowOptimizeModal(false);
    setOptimizationSuggestions([]);
  };

  if (loading) {
    return (
      <PlaybookLoadingView
        error={error}
        onRetry={() => {
          setError(null);
          loadPlaybook(true);
        }}
      />
    );
  }

  if (error || !playbook) {
    return <PlaybookErrorView error={error} />;
  }

  const playbookName = typeof playbook.metadata.name === 'string'
    ? playbook.metadata.name
    : String(playbook.metadata.name || '');

  return (
    <>
      <PlaybookDetailView
        playbook={playbook}
        playbookCode={playbookCode}
        workspaceId={workspaceId}
        playbookList={playbookList}
        recentPlaybooks={recentPlaybooks}
        selectedVersion={selectedVersion}
        onVersionChange={setSelectedVersion}
        onCopyClick={() => setShowCopyModal(true)}
        onLLMClick={() => setShowLLMDrawer(true)}
        isExecuting={isExecuting}
        onExecutePlaybook={handleExecutePlaybook}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isFavorite={isFavorite}
        onToggleFavorite={toggleFavorite}
        onPlaybookSelect={(nextPlaybookCode) => {
          router.push(`/playbooks/${nextPlaybookCode}`, { scroll: false });
        }}
        executionId={executionId}
        initialMessage={initialMessage}
        executionComplete={executionComplete}
        onChatComplete={handleChatComplete}
        onboardingTask={onboardingTask}
        apiUrl={resolveApiBaseUrl(API_URL)}
      />

      <PlaybookDetailModals
        playbookName={playbookName}
        playbookCode={playbookCode}
        systemSOP={playbook.sop_content}
        showCopyModal={showCopyModal}
        onCloseCopyModal={() => setShowCopyModal(false)}
        onConfirmCopy={handleCopySystemVersion}
        showLLMDrawer={showLLMDrawer}
        onCloseLLMDrawer={() => setShowLLMDrawer(false)}
        onVariantCreated={async () => {
          await loadPlaybook();
          await loadVariants();
          setSelectedVersion('personal');
        }}
        showOptimizeModal={showOptimizeModal}
        optimizationLoading={optimizationLoading}
        optimizationSuggestions={optimizationSuggestions}
        onCloseOptimizeModal={closeOptimizeModal}
        onApplySuggestion={handleApplySuggestion}
        showNotesModal={showNotesModal}
        userNotes={userNotes}
        onUserNotesChange={setUserNotes}
        onCloseNotesModal={() => setShowNotesModal(false)}
        onSaveNotes={async () => {
          await saveUserNotes();
          setShowNotesModal(false);
        }}
      />
    </>
  );
}
