import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  Loader2,
  Lock,
  Play,
  Rocket,
  Settings,
  Sparkles,
  Target,
  Unlock,
  Wrench,
  Zap,
} from 'lucide-react';
import ErrorDialog from '@/components/ErrorDialog';
import { useT } from '@/lib/i18n';
import type {
  LaunchpadData,
  WorkspaceHomeDerivedState,
  WorkspaceHomeWorkspace,
} from './workspaceHomeTypes';

interface WorkspaceHomeLaunchpadViewProps {
  workspace: WorkspaceHomeWorkspace | null;
  launchpadData: LaunchpadData | null;
  homeState: WorkspaceHomeDerivedState;
  isLoading: boolean;
  errorMessage: string | null;
  showSetupDrawer: boolean;
  setupSeedText: string;
  isProcessingSeed: boolean;
  errorDialogMessage: string | null;
  onRetry: () => void | Promise<void>;
  onEditBlueprint: () => void;
  onStartWork: () => void;
  onRunFirstPlaybook: () => void;
  onOpenIntents: () => void;
  onOpenSetupDrawer: () => void;
  onCloseSetupDrawer: () => void;
  onSetupSeedTextChange: (value: string) => void;
  onSubmitSetupSeed: () => void | Promise<void>;
  onClearSetupDrawer: () => void;
  onCloseErrorDialog: () => void;
}

const priorityBadgeConfig = {
  high: { color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', icon: AlertCircle },
  medium: { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', icon: Clock },
  low: { color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', icon: CheckCircle2 },
};

const dangerLevelBadgeConfig = {
  low: { color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', label: 'Low Risk' },
  medium: { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Medium Risk' },
  high: { color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', label: 'High Risk' },
};

function PriorityBadge({ priority }: { priority: string }) {
  const { color, icon: Icon } = priorityBadgeConfig[priority as keyof typeof priorityBadgeConfig] || priorityBadgeConfig.low;

  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      <Icon className="w-3 h-3" />
      {priority}
    </span>
  );
}

function DangerLevelBadge({ level }: { level: string }) {
  const { color, label } = dangerLevelBadgeConfig[level.toLowerCase() as keyof typeof dangerLevelBadgeConfig] || dangerLevelBadgeConfig.low;

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

export function WorkspaceHomeLaunchpadView({
  workspace,
  launchpadData,
  homeState,
  isLoading,
  errorMessage,
  showSetupDrawer,
  setupSeedText,
  isProcessingSeed,
  errorDialogMessage,
  onRetry,
  onEditBlueprint,
  onStartWork,
  onRunFirstPlaybook,
  onOpenIntents,
  onOpenSetupDrawer,
  onCloseSetupDrawer,
  onSetupSeedTextChange,
  onSubmitSetupSeed,
  onClearSetupDrawer,
  onCloseErrorDialog,
}: WorkspaceHomeLaunchpadViewProps) {
  const t = useT();
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
          <p className="text-secondary dark:text-gray-400">{t('loadingWorkspace' as any) || 'Loading workspace...'}</p>
        </div>
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950 p-4">
        <div className="max-w-md w-full bg-surface-accent dark:bg-gray-800 rounded-lg border border-red-200 dark:border-red-800 p-6">
          <div className="flex items-center gap-3 mb-4">
            <AlertCircle className="w-6 h-6 text-red-600 dark:text-red-400" />
            <h3 className="text-lg font-semibold text-red-900 dark:text-red-100">
              {t('errorLoadingWorkspace' as any) || 'Error Loading Workspace'}
            </h3>
          </div>
          <p className="text-primary dark:text-gray-300 mb-4">{errorMessage}</p>
          <button
            onClick={onRetry}
            className="w-full px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
          >
            {t('retry' as any) || 'Retry'}
          </button>
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex items-center justify-center h-full min-h-screen bg-gray-50 dark:bg-gray-950">
        <p className="text-secondary dark:text-gray-400">{t('workspaceNotFound' as any) || 'Workspace not found'}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="bg-surface-accent dark:bg-gray-900 border-b border-default dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <h1 className="text-2xl font-bold text-primary dark:text-gray-100 flex items-center gap-2">
                  {workspace.title}
                  {homeState.isReady && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      <CheckCircle2 className="w-3 h-3" />
                      {t('ready' as any)}
                    </span>
                  )}
                  {homeState.isPending && !homeState.hasActualContent && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                      <Clock className="w-3 h-3" />
                      {t('pending' as any)}
                    </span>
                  )}
                  {homeState.launchStatus === 'pending' && homeState.hasActualContent && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      <CheckCircle2 className="w-3 h-3" />
                      {t('ready' as any)}
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
                onClick={onEditBlueprint}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
              >
                <Settings className="w-4 h-4" />
                {t('editBlueprint' as any) || 'Edit Blueprint'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {(!launchpadData || (!homeState.hasContent && homeState.isPending)) ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
            <div className="mb-6 p-4 bg-blue-100 dark:bg-blue-900/30 rounded-full">
              <Sparkles className="w-12 h-12 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-2xl font-bold text-primary dark:text-gray-100 mb-2">{t('workspaceNotConfigured' as any)}</h2>
            <p className="text-secondary dark:text-gray-400 mb-6 max-w-md">{t('workspaceNotConfiguredDescription' as any)}</p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                onClick={onOpenSetupDrawer}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors font-medium"
              >
                <Rocket className="w-5 h-5" />
                {t('configureWorkspace' as any)}
              </button>
              <button
                onClick={onStartWork}
                className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-600 transition-colors font-medium"
              >
                {t('startWorkDirectly' as any)}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {launchpadData?.brief && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <BookOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    {t('workspaceBrief' as any) || 'Workspace Brief'}
                  </h2>
                </div>
                <p className="text-primary dark:text-gray-300 whitespace-pre-line leading-relaxed">{launchpadData.brief}</p>
              </div>
            )}

            {launchpadData?.instruction && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-indigo-200 dark:border-indigo-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">Workspace Instruction</h2>
                </div>
                <div className="space-y-3">
                  {launchpadData.instruction.persona && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Persona</span>
                      <p className="text-primary dark:text-gray-300 mt-0.5">{launchpadData.instruction.persona}</p>
                    </div>
                  )}
                  {launchpadData.instruction.goals && launchpadData.instruction.goals.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Goals</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {launchpadData.instruction.goals.map((goal, index) => (
                          <span key={index} className="px-2 py-0.5 rounded-full text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">{goal}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {launchpadData.instruction.anti_goals && launchpadData.instruction.anti_goals.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Anti-Goals</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {launchpadData.instruction.anti_goals.map((goal, index) => (
                          <span key={index} className="px-2 py-0.5 rounded-full text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">{goal}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {launchpadData.instruction.style_rules && launchpadData.instruction.style_rules.length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Style Rules</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {launchpadData.instruction.style_rules.map((rule, index) => (
                          <span key={index} className="px-2 py-0.5 rounded-full text-xs bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300">{rule}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {launchpadData.instruction.domain_context && (
                    <div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Domain Context</span>
                      <p className="text-sm text-primary dark:text-gray-300 mt-0.5 whitespace-pre-line">{launchpadData.instruction.domain_context}</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {launchpadData?.first_playbook && (
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-200 dark:border-blue-800 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-blue-600 dark:bg-blue-700 rounded-lg">
                      <Play className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-primary dark:text-gray-100">{t('firstPlaybook' as any) || 'First Playbook'}</h3>
                      <p className="text-sm text-secondary dark:text-gray-400">{t('recommendedPlaybook' as any) || 'Recommended playbook to start with'}</p>
                    </div>
                  </div>
                  <div className="mb-4">
                    <p className="text-sm font-medium text-primary dark:text-gray-300 mb-1">{launchpadData.first_playbook}</p>
                  </div>
                  <button
                    onClick={onRunFirstPlaybook}
                    className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors font-medium"
                  >
                    <Zap className="w-4 h-4" />
                    {t('runFirstPlaybook' as any) || 'Run First Playbook'}
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              )}

              <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-800 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-green-600 dark:bg-green-700 rounded-lg">
                    <Rocket className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('startWork' as any) || 'Start Work'}</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{t('startWorkDescription' as any) || 'Enter the workspace to begin working'}</p>
                  </div>
                </div>
                <button
                  onClick={onStartWork}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 bg-green-600 dark:bg-green-700 text-white rounded-lg hover:bg-green-700 dark:hover:bg-green-600 transition-colors font-medium"
                >
                  {t('openWorkspace' as any) || 'Open Workspace'}
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {launchpadData?.initial_intents && launchpadData.initial_intents.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Target className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">{t('nextIntents' as any) || 'Next Intents'}</h2>
                  <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
                    {launchpadData.initial_intents.length} {t('items' as any) || 'items'}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {launchpadData.initial_intents.map((intent, index) => (
                    <div
                      key={index}
                      className="group p-4 bg-surface-secondary dark:bg-gray-800 rounded-lg border border-default dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-md transition-all cursor-pointer"
                      onClick={onOpenIntents}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="font-medium text-primary dark:text-gray-100 flex-1">{intent.title}</h3>
                        <PriorityBadge priority={intent.priority} />
                      </div>
                      {intent.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">{intent.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {launchpadData?.tool_connections && launchpadData.tool_connections.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Wrench className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  <h2 className="text-lg font-semibold text-primary dark:text-gray-100">{t('toolConnections' as any) || 'Tool Connections'}</h2>
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
                            <span className="font-medium text-primary dark:text-gray-100">{tool.tool_type}</span>
                            <DangerLevelBadge level={tool.danger_level} />
                          </div>
                          {tool.allowed_roles && tool.allowed_roles.length > 0 && (
                            <p className="text-xs text-secondary dark:text-gray-400 mt-1">Allowed roles: {tool.allowed_roles.join(', ')}</p>
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

      {showSetupDrawer && (
        <div className="fixed inset-0 z-50 bg-black/50 dark:bg-black/70 flex justify-end" onClick={onCloseSetupDrawer}>
          <div
            className="w-full md:w-2/3 lg:w-1/2 bg-surface-accent dark:bg-gray-900 shadow-lg p-6 overflow-y-auto"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-primary dark:text-gray-100">{t('assembleWorkspace' as any)}</h2>
              <button
                onClick={onCloseSetupDrawer}
                className="p-2 hover:bg-surface-secondary dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                <ArrowRight className="w-5 h-5 text-secondary dark:text-gray-400 rotate-45" />
              </button>
            </div>
            <div className="space-y-4 mb-6">
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h3 className="font-semibold text-primary dark:text-gray-100 mb-2">{t('minimumFileReference' as any)}</h3>
                <p className="text-sm text-secondary dark:text-gray-400 mb-4">{t('minimumFileReferenceDescription' as any)}</p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">{t('pasteText' as any)}</label>
                    <textarea
                      value={setupSeedText}
                      onChange={(event) => onSetupSeedTextChange(event.target.value)}
                      placeholder={t('pasteTextPlaceholder' as any)}
                      rows={8}
                      className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 resize-none"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={onSubmitSetupSeed}
                      disabled={!setupSeedText.trim() || isProcessingSeed}
                      className="flex-1 px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors text-sm font-medium disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                    >
                      {isProcessingSeed ? t('processing' as any) : t('referenceTextToStartWorkspace' as any)}
                    </button>
                    <button
                      onClick={onClearSetupDrawer}
                      className="px-4 py-2 bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-600 transition-colors text-sm font-medium"
                    >
                      {t('close' as any)}
                    </button>
                  </div>
                  <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-secondary dark:text-gray-400 mb-2">{t('otherMethods' as any)}</p>
                    <div className="flex gap-2">
                      <button
                        disabled
                        className="flex-1 px-3 py-2 bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-400 rounded-lg text-xs font-medium cursor-not-allowed"
                      >
                        {t('uploadFile' as any)}
                      </button>
                      <button
                        disabled
                        className="flex-1 px-3 py-2 bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-400 rounded-lg text-xs font-medium cursor-not-allowed"
                      >
                        {t('pasteUrl' as any)}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <ErrorDialog
        isOpen={!!errorDialogMessage}
        onClose={onCloseErrorDialog}
        message={errorDialogMessage || ''}
      />
    </div>
  );
}
