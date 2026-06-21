import Link from 'next/link';
import Header from '../../../components/Header';
import PlaybookChat from '../../../components/PlaybookChat';
import PlaybookDiscoveryChat from '../../../components/playbook/PlaybookDiscoveryChat';
import PlaybookTabs from '../../../components/playbook/PlaybookTabs';
import VersionSelector from '../../../components/playbook/VersionSelector';
import RelatedPlaybooksSidebar from '../../../components/playbooks/RelatedPlaybooksSidebar';
import { t } from '../../../lib/i18n';
import type { Playbook, PlaybookListItem, PlaybookTab, VersionSelection } from './playbookDetailTypes';

export function getPlaybookBadge(playbookCode: string, name?: string): string {
  const source = playbookCode || name || 'PB';
  const badge = source.replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase();
  return badge || 'PB';
}

interface PlaybookLoadingViewProps {
  error: string | null;
  onRetry: () => void;
}

export function PlaybookLoadingView({ error, onRetry }: PlaybookLoadingViewProps) {
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <Header />
      <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12">
          <p className="text-gray-600 dark:text-gray-400">{t('loading' as any)}</p>
          {error && (
            <div className="mt-4">
              <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
              <button
                onClick={onRetry}
                className="mt-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
              >
                {t('retry' as any)}
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

interface PlaybookErrorViewProps {
  error: string | null;
}

export function PlaybookErrorView({ error }: PlaybookErrorViewProps) {
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <Header />
      <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-300">{error || 'Playbook not found'}</p>
        </div>
      </main>
    </div>
  );
}

interface PlaybookDetailViewProps {
  playbook: Playbook;
  playbookCode: string;
  workspaceId: string | null;
  playbookList: PlaybookListItem[];
  recentPlaybooks: PlaybookListItem[];
  selectedVersion: VersionSelection;
  onVersionChange: (version: VersionSelection) => void;
  onCopyClick: () => void;
  onLLMClick: () => void;
  isExecuting: boolean;
  onExecutePlaybook: () => void;
  activeTab: PlaybookTab;
  onTabChange: (tab: PlaybookTab) => void;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onPlaybookSelect: (playbookCode: string) => void;
  executionId: string | null;
  initialMessage: string;
  executionComplete: boolean;
  onChatComplete: (structuredOutput: any) => void | Promise<void>;
  onboardingTask: string | null;
  apiUrl: string;
}

export function PlaybookDetailView({
  playbook,
  playbookCode,
  workspaceId,
  playbookList,
  recentPlaybooks,
  selectedVersion,
  onVersionChange,
  onCopyClick,
  onLLMClick,
  isExecuting,
  onExecutePlaybook,
  activeTab,
  onTabChange,
  isFavorite,
  onToggleFavorite,
  onPlaybookSelect,
  executionId,
  initialMessage,
  executionComplete,
  onChatComplete,
  onboardingTask,
  apiUrl,
}: PlaybookDetailViewProps) {
  const playbookName = playbook.metadata.name;
  const playbookDescription = playbook.metadata.description;
  const playbookTags = playbook.metadata.tags || [];

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950" style={{ scrollBehavior: 'auto' }}>
      <Header />

      <div className="bg-orange-50 dark:bg-orange-900/20 border-b border-orange-200 dark:border-orange-800 sticky top-12 z-40">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
          <div className="flex items-center gap-4">
            <div className="flex-shrink-0 w-48">
              <Link
                href="/playbooks"
                className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                <span>{t('backToList' as any)}</span>
              </Link>
            </div>

            <div className="flex-1 flex justify-center">
              <VersionSelector
                hasPersonalVariant={playbook.version_info?.has_personal_variant || false}
                defaultVariant={playbook.version_info?.default_variant}
                systemVersion={playbook.version_info?.system_version || playbook.metadata.version}
                selectedVersion={selectedVersion}
                onVersionChange={onVersionChange}
                onCopyClick={onCopyClick}
                onLLMClick={onLLMClick}
                activeExecutionsCount={playbook.execution_status?.active_executions?.length || 0}
              />
            </div>

            <div className="flex-shrink-0 w-48 flex justify-end">
              <button
                onClick={onExecutePlaybook}
                disabled={isExecuting}
                className="px-6 py-2.5 bg-accent dark:bg-blue-700 text-white rounded-lg hover:bg-accent/90 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-sm font-medium whitespace-nowrap"
              >
                {isExecuting ? t('executing' as any) : selectedVersion === 'personal' && playbook.version_info?.default_variant
                  ? t('executingVariant', { name: playbook.version_info.default_variant.variant_name })
                  : t('executingInWorkspace' as any)}
              </button>
            </div>
          </div>
        </div>
      </div>

      <main className="w-full">
        <div className="grid grid-cols-12 gap-0">
          <div className="col-span-12 lg:col-span-2">
            <RelatedPlaybooksSidebar
              currentPlaybook={{
                playbook_code: playbook.metadata.playbook_code,
                name: playbook.metadata.name,
                description: playbook.metadata.description,
                icon: playbook.metadata.icon,
                tags: playbook.metadata.tags,
                capability_code: playbook.metadata.capability_code,
              }}
              allPlaybooks={playbookList}
              recentPlaybooks={recentPlaybooks}
            />
          </div>

          <div className="col-span-12 lg:col-span-7">
            <div className="h-[calc(100vh-7rem)] overflow-y-auto">
              <div className="bg-surface-secondary dark:bg-gray-800 shadow p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{playbookName}</h1>
                      <span className="text-sm font-semibold tracking-wide px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                        {getPlaybookBadge(playbook.metadata.playbook_code, playbook.metadata.name)}
                      </span>
                      <button
                        onClick={onToggleFavorite}
                        className="px-2 py-1 text-xs border border-default dark:border-gray-600 rounded hover:bg-tertiary dark:hover:bg-gray-700 transition-colors flex-shrink-0"
                      >
                        {isFavorite ? t('favorites' as any) : t('save' as any)}
                      </button>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{playbookDescription}</p>
                    <div className="flex flex-wrap gap-2">
                      {playbookTags.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-1 bg-surface-accent dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <PlaybookTabs
                activeTab={activeTab}
                onTabChange={onTabChange}
                selectedVersion={selectedVersion}
                playbook={playbook}
                onCopyClick={onCopyClick}
                onLLMClick={onLLMClick}
              />
            </div>
          </div>

          <div className="col-span-12 lg:col-span-3">
            <div className="bg-surface-secondary dark:bg-gray-900 shadow h-[calc(100vh-7rem)] flex flex-col p-4 sticky top-[7rem]">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">{t('findPlaybook' as any)}</h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <PlaybookDiscoveryChat
                  onPlaybookSelect={onPlaybookSelect}
                  currentPlaybookCode={playbookCode}
                  selectedWorkspace={workspaceId || undefined}
                />
              </div>
            </div>
          </div>
        </div>

        {executionId && (
          <div className="bg-surface-secondary dark:bg-gray-800 shadow rounded-lg p-6 mb-6">
            <PlaybookChat
              executionId={executionId}
              playbookCode={playbookCode}
              profileId="default-user"
              initialMessage={initialMessage}
              isComplete={executionComplete}
              onComplete={onChatComplete}
              apiUrl={apiUrl}
            />
            {onboardingTask && !executionComplete && (
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-2">
                {t('willReturnAfterCompletion' as any)}
              </p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
