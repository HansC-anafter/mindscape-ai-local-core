import Header from '../../components/Header';
import ForkPlaybookButton from '../../components/playbooks/ForkPlaybookButton';
import PlaybookLibrarySidebar from '../../components/playbooks/PlaybookLibrarySidebar';
import PlaybookDiscoveryChat from '../../components/playbook/PlaybookDiscoveryChat';
import { WorkspaceSelector } from '../../components/workspace/WorkspaceSelector';
import { useT } from '../../lib/i18n';
import { getPlaybookMetadata } from '../../lib/i18n/locales/playbooks';
import { InstallFromFileButton } from '../settings/components/InstallFromFileButton';
import type { Playbook, PlaybooksByCapability } from './playbooksPageTypes';
import { getPlaybookBadge } from './playbooksPageTransforms';

interface PlaybooksPageViewProps {
  locale: string;
  playbooks: Playbook[];
  filteredPlaybooks: Playbook[];
  playbooksByCapability: PlaybooksByCapability;
  selectedCapability: string;
  onCapabilityChange: (capability: string) => void;
  selectedTags: string[];
  onTagsChange: (tags: string[]) => void;
  selectedWorkspaceId: string | null;
  onWorkspaceChange: (workspaceId: string | null) => void;
  filter: string | null;
  onFilterChange: (filter: string | null) => void;
  searchTerm: string;
  onSearchTermChange: (value: string) => void;
  loading: boolean;
  error: string | null;
  reloading: boolean;
  onReload: () => void | Promise<void>;
  onInstallSuccess: () => void | Promise<void>;
  supportedTestPlaybooks: Set<string>;
  creatingWorkspace: string | null;
  onOpenPlaybook: (playbookCode: string) => void;
  onToggleFavorite: (playbook: Playbook) => void | Promise<void>;
  onExecuteNow: (event: React.MouseEvent, playbook: Playbook) => void | Promise<void>;
  onTogglePin: (playbook: Playbook) => void | Promise<void>;
  onDiscoverPlaybook: (playbookCode: string) => void;
}

export function PlaybooksPageView({
  locale,
  playbooks,
  filteredPlaybooks,
  playbooksByCapability,
  selectedCapability,
  onCapabilityChange,
  selectedTags,
  onTagsChange,
  selectedWorkspaceId,
  onWorkspaceChange,
  filter,
  onFilterChange,
  searchTerm,
  onSearchTermChange,
  loading,
  error,
  reloading,
  onReload,
  onInstallSuccess,
  supportedTestPlaybooks,
  creatingWorkspace,
  onOpenPlaybook,
  onToggleFavorite,
  onExecuteNow,
  onTogglePin,
  onDiscoverPlaybook,
}: PlaybooksPageViewProps) {
  const t = useT();
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <Header />

      <div className="bg-surface-secondary dark:bg-gray-900 border-b border-default dark:border-gray-800">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-bold text-primary dark:text-gray-100 whitespace-nowrap flex-shrink-0">
              {t('playbooksTitle' as any)}
            </h1>

            <div className="hidden xl:flex items-center gap-2 text-xs text-secondary dark:text-gray-400 bg-gradient-to-r from-accent-10 to-surface-secondary dark:from-blue-900/20 dark:to-gray-800/20 rounded-lg px-3 py-1.5 border border-accent/30 dark:border-blue-800 whitespace-nowrap">
              <span>{t('playbookStepMindscape' as any)}</span>
              <span className="text-tertiary dark:text-gray-500">&gt;</span>
              <span>{t('playbookStepTools' as any)}</span>
              <span className="text-tertiary dark:text-gray-500">&gt;</span>
              <span>{t('playbookStepMembers' as any)}</span>
            </div>

            <div className="hidden md:block flex-shrink-0">
              <WorkspaceSelector
                ownerUserId="default-user"
                value={selectedWorkspaceId || ''}
                onValueChange={(workspaceId) => onWorkspaceChange(workspaceId || null)}
                showLabel={false}
                className="min-w-[160px] max-w-[200px]"
              />
            </div>

            <div className="flex-1" />

            <input
              type="text"
              placeholder={t('searchPlaybooks' as any)}
              value={searchTerm}
              onChange={(event) => onSearchTermChange(event.target.value)}
              className="w-36 lg:w-48 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
            />

            <button
              onClick={onReload}
              disabled={reloading || loading}
              className="px-3 py-1.5 text-sm bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              {reloading ? t('reloading' as any) : t('reload' as any)}
            </button>

            <InstallFromFileButton onSuccess={onInstallSuccess} />
          </div>

          {error && (
            <div className="mt-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
            </div>
          )}
        </div>
      </div>

      <main className="w-full">
        <div className="grid grid-cols-12 gap-0">
          <div className="col-span-12 lg:col-span-2">
            <PlaybookLibrarySidebar
              playbooks={playbooks}
              selectedTags={selectedTags}
              onTagsChange={onTagsChange}
              selectedWorkspaceId={selectedWorkspaceId}
              onWorkspaceChange={onWorkspaceChange}
              selectedCapability={selectedCapability}
              onCapabilityChange={onCapabilityChange}
              playbooksByCapability={playbooksByCapability}
              filter={filter || undefined}
              onFilterChange={onFilterChange}
              profileId="default-user"
            />
          </div>

          <div className="col-span-12 lg:col-span-7">
            <div className="h-[calc(100vh-8rem)] flex flex-col">
              {loading ? (
                <div className="p-4">
                  <p className="text-secondary dark:text-gray-400">{t('loading' as any)}</p>
                </div>
              ) : filteredPlaybooks.length === 0 ? (
                <div className="p-4">
                  <div className="bg-surface-accent dark:bg-gray-800 shadow rounded-lg p-12 text-center">
                    <p className="text-secondary dark:text-gray-400">{t('noPlaybooksFound' as any)}</p>
                  </div>
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto p-4">
                  {playbooksByCapability[selectedCapability] && playbooksByCapability[selectedCapability].length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                      {playbooksByCapability[selectedCapability].map((playbook) => (
                        <PlaybookCard
                          key={playbook.playbook_code}
                          locale={locale}
                          playbook={playbook}
                          selectedWorkspaceId={selectedWorkspaceId}
                          supportedTestPlaybooks={supportedTestPlaybooks}
                          creatingWorkspace={creatingWorkspace}
                          onOpenPlaybook={onOpenPlaybook}
                          onToggleFavorite={onToggleFavorite}
                          onExecuteNow={onExecuteNow}
                          onTogglePin={onTogglePin}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="bg-surface-secondary dark:bg-gray-800 shadow rounded-lg p-12 text-center">
                      <p className="text-secondary dark:text-gray-400">{t('noPlaybooksFound' as any)}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-3">
            <div className="bg-surface-secondary dark:bg-gray-900 shadow h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-0">
              <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">{t('findPlaybook' as any)}</h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <PlaybookDiscoveryChat
                  onPlaybookSelect={onDiscoverPlaybook}
                  selectedCapability={selectedCapability}
                  selectedWorkspace={selectedWorkspaceId ?? undefined}
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

interface PlaybookCardProps {
  locale: string;
  playbook: Playbook;
  selectedWorkspaceId: string | null;
  supportedTestPlaybooks: Set<string>;
  creatingWorkspace: string | null;
  onOpenPlaybook: (playbookCode: string) => void;
  onToggleFavorite: (playbook: Playbook) => void | Promise<void>;
  onExecuteNow: (event: React.MouseEvent, playbook: Playbook) => void | Promise<void>;
  onTogglePin: (playbook: Playbook) => void | Promise<void>;
}

function PlaybookCard({
  locale,
  playbook,
  selectedWorkspaceId,
  supportedTestPlaybooks,
  creatingWorkspace,
  onOpenPlaybook,
  onToggleFavorite,
  onExecuteNow,
  onTogglePin,
}: PlaybookCardProps) {
  const t = useT();
  const isPinned = playbook.pinned_workspaces?.some((workspace) => workspace.id === selectedWorkspaceId) || false;

  return (
    <div
      className="bg-surface-secondary dark:bg-gray-800 rounded-lg shadow p-6 hover:shadow-lg transition-shadow flex flex-col cursor-pointer border border-default dark:border-gray-700"
      onClick={() => onOpenPlaybook(playbook.playbook_code)}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold tracking-wide px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
            {getPlaybookBadge(playbook)}
          </span>
          {playbook.scope && (
            <span className={`text-xs px-2 py-1 rounded ${playbook.scope === 'system'
              ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
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
              {t('systemPlaybook' as any)}
            </span>
          )}
          {supportedTestPlaybooks.has(playbook.playbook_code) && (
            <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded flex items-center gap-1">
              Test {t('hasTest' as any)}
            </span>
          )}
        </div>
        <button
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggleFavorite(playbook);
          }}
          className="text-2xl hover:scale-110 transition-transform flex-shrink-0"
        >
          {playbook.user_meta?.favorite ? t('favorites' as any) : ''}
        </button>
      </div>

      <h3 className="font-semibold text-lg mb-2 min-h-[3rem] text-gray-900 dark:text-gray-100">
        {getPlaybookMetadata(playbook.playbook_code, 'name', locale as 'zh-TW' | 'en' | 'ja') || playbook.name}
      </h3>

      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 line-clamp-2 flex-grow">
        {getPlaybookMetadata(playbook.playbook_code, 'description', locale as 'zh-TW' | 'en' | 'ja') || playbook.description}
      </p>

      <div className="flex flex-wrap gap-2 mb-3 min-h-[1.5rem]">
        {playbook.has_personal_variant && (
          <span className="text-xs px-2 py-1 bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300 rounded">
            {t('hasPersonalVariant' as any)}
          </span>
        )}
        {(playbook.tags || []).slice(0, 2).map((tag) => (
          <span
            key={tag}
            className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 rounded"
          >
            {tag}
          </span>
        ))}
      </div>

      {playbook.onboarding_task && (
        <div className="text-xs text-accent dark:text-blue-400 font-medium mb-2">
          {t('coldStartTask' as any)} {playbook.onboarding_task.replace('task', '')}
        </div>
      )}

      {(playbook.workspace_usage_count !== undefined && playbook.workspace_usage_count > 0) ||
        (playbook.pinned_workspaces && playbook.pinned_workspaces.length > 0) ||
        selectedWorkspaceId ? (
        <div className="mb-3 pt-3 border-t border-gray-100 dark:border-gray-700">
          {playbook.workspace_usage_count !== undefined && playbook.workspace_usage_count > 0 && (
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
              {t('usedInWorkspaces', { count: String(playbook.workspace_usage_count) })}
            </div>
          )}
          <div className="text-xs text-gray-600 dark:text-gray-400 flex items-center justify-between">
            {playbook.pinned_workspaces && playbook.pinned_workspaces.length > 0 ? (
              <span>
                {t('pinnedIn', {
                  workspaces: playbook.pinned_workspaces.slice(0, 2).map((workspace) => workspace.title).join(', ') +
                    (playbook.pinned_workspaces.length > 2 ? ` +${playbook.pinned_workspaces.length - 2}` : '')
                })}
              </span>
            ) : selectedWorkspaceId ? (
              <span className="text-gray-400 dark:text-gray-500">{t('notPinned' as any)}</span>
            ) : null}
            {selectedWorkspaceId && (
              <button
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onTogglePin(playbook);
                }}
                className="ml-2 text-xs px-2 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 border border-default dark:border-gray-600"
                title={isPinned ? t('unpin' as any) : t('pin' as any)}
              >
                {isPinned ? t('unpin' as any) : t('pin' as any)}
              </button>
            )}
          </div>
        </div>
      ) : null}

      <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-100 dark:border-gray-700">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {playbook.user_meta?.use_count || 0} {t('times' as any)}
        </span>
        <div className="flex items-center gap-2">
          {playbook.scope && playbook.scope !== 'workspace' && (
            <ForkPlaybookButton
              playbookCode={playbook.playbook_code}
              playbookName={playbook.name}
            />
          )}
          <button
            onClick={(event) => onExecuteNow(event, playbook)}
            disabled={creatingWorkspace === playbook.playbook_code}
            className="px-3 py-1 text-xs bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
          >
            {creatingWorkspace === playbook.playbook_code ? t('creating' as any) : t('executeNow' as any)}
          </button>
        </div>
      </div>
    </div>
  );
}
