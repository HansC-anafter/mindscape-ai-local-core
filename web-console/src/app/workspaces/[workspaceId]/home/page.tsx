'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { t } from '@/lib/i18n';
import {
  Rocket,
  Target,
  Play,
  Settings,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Clock,
  FileText,
  Zap,
  Lock,
  Unlock,
  Loader2,
  Sparkles,
  BookOpen,
  Wrench,
  ArrowLeft
} from 'lucide-react';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

interface IntentCard {
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
}

interface ToolConnectionDisplay {
  tool_type: string;
  danger_level: string;
  default_readonly: boolean;
  allowed_roles: string[];
}

interface LaunchpadData {
  brief: string | null;
  initial_intents: IntentCard[];
  first_playbook: string | null;
  tool_connections: ToolConnectionDisplay[];
  launch_status: string;
  starter_kit_type?: string;
}

const PriorityBadge = ({ priority }: { priority: string }) => {
  const config = {
    high: { color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', icon: AlertCircle },
    medium: { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', icon: Clock },
    low: { color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', icon: CheckCircle2 }
  };

  const { color, icon: Icon } = config[priority as keyof typeof config] || config.low;

  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      <Icon className="w-3 h-3" />
      {priority}
    </span>
  );
};

const DangerLevelBadge = ({ level }: { level: string }) => {
  const config = {
    low: { color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', label: 'Low Risk' },
    medium: { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Medium Risk' },
    high: { color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', label: 'High Risk' }
  };

  const { color, label } = config[level.toLowerCase() as keyof typeof config] || config.low;

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
};

export default function WorkspaceHomePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params?.workspaceId as string;
  const isNewWorkspace = workspaceId === 'new';
  // Use optional hook to avoid errors when workspaceId is 'new'
  const workspaceData = useWorkspaceDataOptional();
  const workspace = workspaceData?.workspace || null;
  const isLoadingWorkspace = isNewWorkspace ? false : (workspaceData?.isLoadingWorkspace || false);
  const workspaceError = workspaceData?.error || null;
  const refreshWorkspace = workspaceData?.refreshWorkspace || null;
  const [launchpadData, setLaunchpadData] = useState<LaunchpadData | null>(null);
  const [isLoadingLaunchpad, setIsLoadingLaunchpad] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSetupDrawer, setShowSetupDrawer] = useState(false);
  const [setupSeedText, setSetupSeedText] = useState<string>('');
  const [isProcessingSeed, setIsProcessingSeed] = useState(false);

  // Wizard state for new workspace creation
  const [wizardStep, setWizardStep] = useState<'method' | 'seed' | 'preview' | 'complete'>(isNewWorkspace ? 'method' : 'complete');
  const [wizardData, setWizardData] = useState<{
    method?: 'quick' | 'llm-guided';
    title?: string;
    description?: string;
    seedType?: 'text' | 'file' | 'urls';
    seedPayload?: any;
  }>({});
  const [wizardSeedText, setWizardSeedText] = useState<string>('');

  useEffect(() => {
    if (searchParams?.get('setup') === 'true') {
      setShowSetupDrawer(true);
      // Optionally remove the query param after handling
      const newSearchParams = new URLSearchParams(searchParams.toString());
      newSearchParams.delete('setup');
      router.replace(`${window.location.pathname}?${newSearchParams.toString()}`);
    }
  }, [searchParams, router]);

  // For new workspace, always show wizard
  useEffect(() => {
    if (isNewWorkspace) {
      setWizardStep('method');
    }
  }, [isNewWorkspace]);

  // For new workspace, always show wizard
  useEffect(() => {
    if (isNewWorkspace) {
      setWizardStep('method');
    }
  }, [isNewWorkspace]);

  const fetchLaunchpadData = useCallback(async () => {
    if (!workspaceId || isNewWorkspace) return;
    setIsLoadingLaunchpad(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/launchpad`);
      if (!response.ok) {
        // Handle 404 - workspace not found or no blueprint
        if (response.status === 404) {
          // Return empty launchpad data instead of error
          setLaunchpadData({
            brief: null,
            initial_intents: [],
            first_playbook: null,
            tool_connections: [],
            launch_status: 'pending'
          });
          return;
        }
        let errorData;
        try {
          errorData = await response.json();
        } catch {
          errorData = { detail: `HTTP ${response.status}: ${response.statusText}` };
        }
        throw new Error(errorData.detail || 'Failed to fetch launchpad data');
      }
      const data: LaunchpadData = await response.json();
      setLaunchpadData(data);
    } catch (err) {
      console.error('Error fetching launchpad data:', err);
      // Don't set error for 404, just show empty state
      if (err instanceof Error && err.message.includes('404')) {
        setLaunchpadData({
          brief: null,
          initial_intents: [],
          first_playbook: null,
          tool_connections: [],
          launch_status: 'pending'
        });
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setIsLoadingLaunchpad(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (workspaceId && !isLoadingWorkspace) {
      fetchLaunchpadData();
    }
  }, [workspaceId, isLoadingWorkspace, fetchLaunchpadData]);

  const handleStartWork = () => {
    if (workspaceId) {
      router.push(`/workspaces/${workspaceId}`);
    }
  };

  const handleRunFirstPlaybook = () => {
    if (workspaceId && launchpadData?.first_playbook) {
      router.push(`/workspaces/${workspaceId}/playbook/${launchpadData.first_playbook}`);
    }
  };

  const handleEditBlueprint = () => {
    setShowSetupDrawer(true);
  };

  // Show wizard for new workspace
  if (isNewWorkspace) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {wizardStep === 'method' && (
            <div className="max-w-6xl mx-auto">
              <div className="flex items-center gap-4 mb-6">
                <button
                  onClick={() => router.push('/workspaces')}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  {t('back')}
                </button>
                <h1 className="text-3xl font-bold text-primary dark:text-gray-100">{t('createWorkspace')}</h1>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-surface-accent dark:bg-gray-900 rounded-lg border border-default dark:border-gray-800 p-6 shadow-sm">
                  <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">{t('selectCreationMethod')}</h2>
                  <div className="space-y-4">
                    <button
                      onClick={() => {
                        setWizardData({ method: 'quick' });
                      }}
                      className={`w-full p-4 text-left border-2 rounded-lg transition-colors ${
                        wizardData.method === 'quick'
                          ? 'border-blue-500 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                          : 'border-default dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-600'
                      }`}
                    >
                      <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('quickCreate')}</h3>
                      <p className="text-sm text-secondary dark:text-gray-400">{t('quickCreateDescription')}</p>
                    </button>
                    <button
                      onClick={() => {
                        setWizardData({ method: 'llm-guided' });
                      }}
                      className={`w-full p-4 text-left border-2 rounded-lg transition-colors ${
                        wizardData.method === 'llm-guided'
                          ? 'border-blue-500 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                          : 'border-default dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-600'
                      }`}
                    >
                      <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('llmGuidedCreate')}</h3>
                      <p className="text-sm text-secondary dark:text-gray-400">{t('llmGuidedCreateDescription')}</p>
                    </button>
                  </div>
                </div>

                <div className="bg-surface-accent dark:bg-gray-900 rounded-lg border border-default dark:border-gray-800 p-6 shadow-sm">
                  {!wizardData.method ? (
                    <div className="flex items-center justify-center h-full min-h-[200px] text-secondary dark:text-gray-400">
                      <p>{t('pleaseSelectCreationMethod')}</p>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {/* Basic Information */}
                      <div>
                        <div className="flex items-center justify-between mb-4">
                          <h2 className="text-xl font-semibold text-primary dark:text-gray-100">
                            {wizardData.method === 'quick' ? t('quickCreate') : t('llmGuidedCreate')}
                          </h2>
                          <button
                            onClick={() => setWizardData({ ...wizardData, method: undefined })}
                            className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
                          >
                            <ArrowLeft className="w-4 h-4" />
                            {t('previous')}
                          </button>
                        </div>
                        <div className="space-y-4">
                          <div>
                            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
                              {t('workspaceNameRequired')}
                            </label>
                            <input
                              type="text"
                              value={wizardData.title || ''}
                              onChange={(e) => setWizardData({ ...wizardData, title: e.target.value })}
                              placeholder={t('workspaceNamePlaceholder')}
                              className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-100"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
                              {wizardData.method === 'quick' ? t('workspaceDescriptionOptional') : t('workspaceDescriptionRequired')}
                              {wizardData.method === 'llm-guided' && <span className="text-red-500">*</span>}
                            </label>
                            <textarea
                              value={wizardData.description || ''}
                              onChange={(e) => setWizardData({ ...wizardData, description: e.target.value })}
                              placeholder={wizardData.method === 'quick'
                                ? t('workspaceDescriptionPlaceholder')
                                : t('workspaceDescriptionLLMPlaceholder')}
                              rows={wizardData.method === 'quick' ? 3 : 5}
                              className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-100"
                            />
                          </div>
                        </div>
                      </div>

                      {/* Seed Input (Optional) */}
                      <div className="border-t border-default dark:border-gray-700 pt-6">
                        <h3 className="text-lg font-semibold text-primary dark:text-gray-100 mb-2">{t('addReferenceSeed')}</h3>
                        <p className="text-sm text-secondary dark:text-gray-400 mb-4">
                          {t('addReferenceSeedDescription')}
                        </p>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            {t('pasteText')}
                          </label>
                          <textarea
                            value={wizardSeedText}
                            onChange={(e) => setWizardSeedText(e.target.value)}
                            placeholder={t('pasteTextPlaceholder')}
                            rows={5}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          />
                        </div>
                      </div>

                      {/* Complete Button */}
                      <div className="border-t border-default dark:border-gray-700 pt-6">
                        <button
                          onClick={async () => {
                            const requiredFields = wizardData.method === 'quick'
                              ? wizardData.title
                              : wizardData.title && wizardData.description;

                            if (!requiredFields) return;

                            try {
                              // Create workspace
                              const createResponse = await fetch(`${API_URL}/api/v1/workspaces?owner_user_id=default-user`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  title: wizardData.title,
                                  description: wizardData.description || ''
                                })
                              });
                              if (!createResponse.ok) {
                                const errorData = await createResponse.json().catch(() => ({ detail: createResponse.statusText }));
                                throw new Error(errorData.detail || errorData.message || `Failed to create workspace: ${createResponse.status}`);
                              }
                              const newWorkspace = await createResponse.json();

                              // Process seed if provided
                              if (wizardSeedText.trim()) {
                                await fetch(`${API_URL}/api/v1/workspaces/${newWorkspace.id}/seed`, {
                                  method: 'POST',
                                  headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({
                                    seed_type: 'text',
                                    payload: wizardSeedText,
                                    locale: 'zh-TW'
                                  })
                                });
                              }

                              // Redirect to the new workspace's launchpad
                              router.push(`/workspaces/${newWorkspace.id}/home`);
                            } catch (err) {
                              alert(t('creationFailed') + ': ' + (err instanceof Error ? err.message : String(err)));
                            }
                          }}
                          disabled={
                            wizardData.method === 'quick'
                              ? !wizardData.title
                              : !wizardData.title || !wizardData.description
                          }
                          className="w-full px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                        >
                          {t('createAndComplete')}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    );
  }

  if (isLoadingWorkspace || isLoadingLaunchpad) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
          <p className="text-secondary dark:text-gray-400">{t('loadingWorkspace') || 'Loading workspace...'}</p>
        </div>
      </div>
    );
  }

  if (workspaceError || error) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950 p-4">
        <div className="max-w-md w-full bg-surface-accent dark:bg-gray-800 rounded-lg border border-red-200 dark:border-red-800 p-6">
          <div className="flex items-center gap-3 mb-4">
            <AlertCircle className="w-6 h-6 text-red-600 dark:text-red-400" />
            <h3 className="text-lg font-semibold text-red-900 dark:text-red-100">
              {t('errorLoadingWorkspace') || 'Error Loading Workspace'}
            </h3>
          </div>
          <p className="text-primary dark:text-gray-300 mb-4">
            {workspaceError || error}
          </p>
          <button
            onClick={refreshWorkspace || fetchLaunchpadData}
            className="w-full px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
          >
            {t('retry') || 'Retry'}
          </button>
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950">
        <p className="text-secondary dark:text-gray-400">{t('workspaceNotFound') || 'Workspace not found'}</p>
      </div>
    );
  }

  // Use workspace.launch_status as fallback if launchpadData is not loaded yet
  const launchStatus = launchpadData?.launch_status || (workspace as any)?.launch_status || 'pending';

  // Check if workspace actually has content (brief or intents)
  const hasActualContent = launchpadData && (
    (launchpadData.brief && launchpadData.brief.trim().length > 0) ||
    (launchpadData.initial_intents && launchpadData.initial_intents.length > 0) ||
    (launchpadData.tool_connections && launchpadData.tool_connections.length > 0)
  );

  // Fallback: Even if launch_status is 'pending', if there is actual content, show content instead of empty state
  // This can happen when workspace has blueprint content but status is not correctly updated
  const isPending = launchStatus === 'pending' && !hasActualContent;
  const isReady = launchStatus === 'ready' || (launchStatus === 'pending' && hasActualContent);

  // For pending workspaces without content, show empty state
  // For ready/active workspaces OR pending workspaces with actual content, show content
  const hasContent = hasActualContent || (!isPending && launchpadData);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <div className="bg-surface-accent dark:bg-gray-900 border-b border-default dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <h1 className="text-2xl font-bold text-primary dark:text-gray-100 flex items-center gap-2">
                  {workspace.title}
                  {isReady && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      <CheckCircle2 className="w-3 h-3" />
                      {t('ready')}
                    </span>
                  )}
                  {isPending && !hasActualContent && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                      <Clock className="w-3 h-3" />
                      {t('pending')}
                    </span>
                  )}
                  {launchStatus === 'pending' && hasActualContent && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      <CheckCircle2 className="w-3 h-3" />
                      {t('ready')}
                    </span>
                  )}
                </h1>
                {workspace.description && (
                  <p className="text-sm text-secondary dark:text-gray-400 mt-1">{workspace.description}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleEditBlueprint}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
              >
                <Settings className="w-4 h-4" />
                {t('editBlueprint') || 'Edit Blueprint'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Show empty state if pending and no content, OR if launchpadData is null (still loading or failed) */}
        {(!launchpadData || (!hasContent && isPending)) ? (
          /* Empty State - Pending Setup */
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
            <div className="mb-6 p-4 bg-blue-100 dark:bg-blue-900/30 rounded-full">
              <Sparkles className="w-12 h-12 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-2xl font-bold text-primary dark:text-gray-100 mb-2">
              {t('workspaceNotConfigured')}
            </h2>
            <p className="text-secondary dark:text-gray-400 mb-6 max-w-md">
              {t('workspaceNotConfiguredDescription')}
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => setShowSetupDrawer(true)}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors font-medium"
              >
                <Rocket className="w-5 h-5" />
                {t('configureWorkspace')}
              </button>
              <button
                onClick={handleStartWork}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-600 transition-colors font-medium"
              >
                {t('startWorkDirectly')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Workspace Brief */}
            {launchpadData?.brief && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <BookOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    {t('workspaceBrief') || 'Workspace Brief'}
                  </h2>
                </div>
                <p className="text-primary dark:text-gray-300 whitespace-pre-line leading-relaxed">
                  {launchpadData.brief}
                </p>
              </div>
            )}

            {/* Main Actions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* First Playbook CTA */}
              {launchpadData?.first_playbook && (
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-200 dark:border-blue-800 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-blue-600 dark:bg-blue-700 rounded-lg">
                      <Play className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-primary dark:text-gray-100">
                        {t('firstPlaybook') || 'First Playbook'}
                      </h3>
                      <p className="text-sm text-secondary dark:text-gray-400">
                        {t('recommendedPlaybook') || 'Recommended playbook to start with'}
                      </p>
                    </div>
                  </div>
                  <div className="mb-4">
                    <p className="text-sm font-medium text-primary dark:text-gray-300 mb-1">
                      {launchpadData.first_playbook}
                    </p>
                  </div>
                  <button
                    onClick={handleRunFirstPlaybook}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors font-medium"
                  >
                    <Zap className="w-4 h-4" />
                    {t('runFirstPlaybook') || 'Run First Playbook'}
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* Start Work CTA */}
              <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-800 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-green-600 dark:bg-green-700 rounded-lg">
                    <Rocket className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {t('startWork') || 'Start Work'}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('startWorkDescription') || 'Enter the workspace to begin working'}
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleStartWork}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 bg-green-600 dark:bg-green-700 text-white rounded-lg hover:bg-green-700 dark:hover:bg-green-600 transition-colors font-medium"
                >
                  {t('openWorkspace') || 'Open Workspace'}
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Initial Intents */}
            {launchpadData?.initial_intents && launchpadData.initial_intents.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    {t('nextIntents') || 'Next Intents'}
                  </h2>
                  <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
                    {launchpadData.initial_intents.length} {t('items') || 'items'}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {launchpadData.initial_intents.map((intent, index) => (
                    <div
                      key={index}
                      className="group p-4 bg-surface-secondary dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-md transition-all cursor-pointer"
                      onClick={() => router.push(`/workspaces/${workspaceId}/intents`)}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="font-medium text-primary dark:text-gray-100 flex-1">
                          {intent.title}
                        </h3>
                        <PriorityBadge priority={intent.priority} />
                      </div>
                      {intent.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                          {intent.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tool Connections */}
            {launchpadData?.tool_connections && launchpadData.tool_connections.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Wrench className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    {t('toolConnections') || 'Tool Connections'}
                  </h2>
                </div>
                <div className="space-y-3">
                  {launchpadData.tool_connections.map((tool, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-4 bg-surface-secondary dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-surface-secondary dark:bg-gray-700 rounded-lg">
                          <Wrench className="w-4 h-4 text-secondary dark:text-gray-400" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-primary dark:text-gray-100">
                              {tool.tool_type}
                            </span>
                            <DangerLevelBadge level={tool.danger_level} />
                          </div>
                          {tool.allowed_roles && tool.allowed_roles.length > 0 && (
                            <p className="text-xs text-secondary dark:text-gray-400 mt-1">
                              Allowed roles: {tool.allowed_roles.join(', ')}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {tool.default_readonly ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                            <Lock className="w-3 h-3" />
                            Read-only
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                            <Unlock className="w-3 h-3" />
                            Writable
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Setup Drawer (for pending workspaces) */}
      {showSetupDrawer && (
        <div className="fixed inset-0 z-50 bg-black/50 dark:bg-black/70 flex justify-end" onClick={() => setShowSetupDrawer(false)}>
          <div
            className="w-full md:w-2/3 lg:w-1/2 bg-surface-accent dark:bg-gray-900 shadow-lg p-6 overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-primary dark:text-gray-100">
                {t('assembleWorkspace')}
              </h2>
              <button
                onClick={() => setShowSetupDrawer(false)}
                className="p-2 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                <ArrowRight className="w-5 h-5 text-secondary dark:text-gray-400 rotate-45" />
              </button>
            </div>
            <div className="space-y-4 mb-6">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('minimumFileReference')}</h3>
                <p className="text-sm text-secondary dark:text-gray-400 mb-4">
                  {t('minimumFileReferenceDescription')}
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
                      {t('pasteText')}
                    </label>
                    <textarea
                      value={setupSeedText}
                      onChange={(e) => setSetupSeedText(e.target.value)}
                      placeholder={t('pasteTextPlaceholder')}
                      rows={8}
                      className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 resize-none"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        if (!setupSeedText.trim() || !workspaceId) return;
                        setIsProcessingSeed(true);
                        try {
                          const response = await fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/seed`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ seed_type: 'text', payload: setupSeedText.trim(), locale: 'zh-TW' })
                          });
                          if (response.ok) {
                            await fetchLaunchpadData();
                            setSetupSeedText('');
                            setShowSetupDrawer(false);
                            alert(t('workspaceConfigured'));
                          } else {
                            const errorData = await response.json().catch(() => ({ detail: response.statusText }));
                            alert(t('configurationFailed') + ': ' + (errorData.detail || errorData.message || t('retry')));
                          }
                        } catch (err) {
                          alert(t('configurationFailed') + ': ' + (err instanceof Error ? err.message : String(err)));
                        } finally {
                          setIsProcessingSeed(false);
                        }
                      }}
                      disabled={!setupSeedText.trim() || isProcessingSeed}
                      className="flex-1 px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors text-sm font-medium disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                    >
                      {isProcessingSeed ? t('processing') : t('referenceTextToStartWorkspace')}
                    </button>
                    <button
                      onClick={() => {
                        setSetupSeedText('');
                        setShowSetupDrawer(false);
                      }}
                      className="px-4 py-2 bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-600 transition-colors text-sm font-medium"
                    >
                      {t('close')}
                    </button>
                  </div>
                  <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-secondary dark:text-gray-400 mb-2">{t('otherMethods')}</p>
                    <div className="flex gap-2">
                      <button
                        disabled
                        className="flex-1 px-3 py-2 bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-400 rounded-lg text-xs font-medium cursor-not-allowed"
                      >
                        {t('uploadFile')}
                      </button>
                      <button
                        disabled
                        className="flex-1 px-3 py-2 bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-400 rounded-lg text-xs font-medium cursor-not-allowed"
                      >
                        {t('pasteUrl')}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
