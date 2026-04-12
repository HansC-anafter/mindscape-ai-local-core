'use client';

import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import IGGridView from './IGGridView';
import TimelineView from './views/TimelineView';
import KanbanView from './views/KanbanView';
import SeriesPanel from './modules/SeriesPanel';
import ProducePanel from './modules/ProducePanel';
import AssetsPanel from './modules/AssetsPanel';
import ReviewPanel from './modules/ReviewPanel';
import ExportPanel from './modules/ExportPanel';
import PublishPanel from './modules/PublishPanel';
import MeasurePanel from './modules/MeasurePanel';
import EngagePanel from './modules/EngagePanel';
import ReferencesPanel from './modules/ReferencesPanel';
import type { IGWorkbenchProps } from './workbench/types';
import { WORKBENCH_MODULES } from './workbench/moduleRegistry';
import { useIGWorkbenchState } from './workbench/hooks/useIGWorkbenchState';
import { WorkbenchSidebar } from './workbench/components/WorkbenchSidebar';
import { WorkbenchHeader } from './workbench/components/WorkbenchHeader';
import { WorkbenchExecutionPanel } from './workbench/components/WorkbenchExecutionPanel';
import { useBrowserSessionStatus } from './modules/accounts/hooks/useBrowserSessionStatus';
import { resolveWorkspaceIGUserDataDir } from './browserProfile';
import {
  fetchIGVisionRuntimePolicy,
  saveIGVisionRuntimePolicy,
  type IGVisionExecutionMode,
} from './visionExecution';

const AccountsPanel = lazy(() => import('./modules/AccountsPanel'));
const AccessPanel = lazy(() => import('./modules/AccessPanel'));
const ManagedAccountsPanel = lazy(() => import('./modules/ManagedAccountsPanel'));

export default function IGWorkbench({
  workspaceId,
  apiUrl
}: IGWorkbenchProps) {
  const [visionExecutionMode, setVisionExecutionModeState] = useState<IGVisionExecutionMode>('local');
  const [visionExecutionModeSaving, setVisionExecutionModeSaving] = useState(false);
  const {
    baseApiUrl,
    activeModule,
    setActiveModule,
    viewMode,
    setViewMode,
    statusFilter,
    setStatusFilter,
    selectedPostId,
    setSelectedPostId,
    selectedAccountId,
    setSelectedAccountId,
    posts,
    postsLoading,
    statusButtons,
    runLogCounts,
    targetsTotal,
    recentRuns,
    recentGroups,
    isRunning,
    error,
    setError,
    loadPosts,
    loadRecentRuns,
    getSelectedPost,
    handleRunPlaybook,
  } = useIGWorkbenchState({ workspaceId, apiUrl });
  const browserProfile = useBrowserSessionStatus(baseApiUrl, workspaceId);
  const {
    browserSession,
    profileName,
    profilePathInput,
    setProfilePathInput,
    setWorkspaceProfileName,
    setWorkspaceProfilePathOverride,
    checkBrowserSessionStatus,
    availableProfiles,
    selectedProfileInfo,
    loadProfiles,
  } = browserProfile;

  // Auto-switch to accounts module when scroll-to-account event fires
  const activeModuleRef = useRef(activeModule);
  activeModuleRef.current = activeModule;

  const handleOpenFollowingAnalyzer = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (activeModuleRef.current !== 'discovery') {
      setActiveModule('discovery');
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('ig:open-following-analyzer'));
      }, 300);
      return;
    }
    window.dispatchEvent(new CustomEvent('ig:open-following-analyzer'));
  }, [setActiveModule]);

  const handleSelectActiveProfile = useCallback((nextProfileName: string) => {
    setWorkspaceProfileName(nextProfileName);
    void checkBrowserSessionStatus(resolveWorkspaceIGUserDataDir(workspaceId));
  }, [checkBrowserSessionStatus, setWorkspaceProfileName, workspaceId]);

  const handleRefreshActiveProfile = useCallback(() => {
    void loadProfiles();
    void checkBrowserSessionStatus(
      (browserSession.profilePath || '').trim() || resolveWorkspaceIGUserDataDir(workspaceId)
    );
  }, [browserSession.profilePath, checkBrowserSessionStatus, loadProfiles, workspaceId]);

  useEffect(() => {
    let mounted = true;
    void fetchIGVisionRuntimePolicy(baseApiUrl, workspaceId)
      .then((policy) => {
        if (!mounted) return;
        setVisionExecutionModeState(policy.visionExecutionMode);
      })
      .catch((error) => {
        console.warn('Failed to load IG vision runtime policy:', error);
      });
    return () => {
      mounted = false;
    };
  }, [baseApiUrl, workspaceId]);

  const handleVisionExecutionModeChange = useCallback((nextMode: IGVisionExecutionMode) => {
    const previousMode = visionExecutionMode;
    setVisionExecutionModeState(nextMode);
    setVisionExecutionModeSaving(true);
    void saveIGVisionRuntimePolicy(baseApiUrl, {
      workspaceId,
      visionExecutionMode: nextMode,
    })
      .then((policy) => {
        setVisionExecutionModeState(policy.visionExecutionMode);
      })
      .catch((error) => {
        console.warn('Failed to save IG vision runtime policy:', error);
        setVisionExecutionModeState(previousMode);
      })
      .finally(() => {
        setVisionExecutionModeSaving(false);
      });
  }, [baseApiUrl, visionExecutionMode, workspaceId]);

  useEffect(() => {
    void checkBrowserSessionStatus();
  }, [checkBrowserSessionStatus]);

  useEffect(() => {
    const handler = (e: Event) => {
      if (activeModuleRef.current !== 'discovery') {
        setActiveModule('discovery');
        // Re-dispatch after AccountsPanel mounts
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('ig:scroll-to-account', { detail: (e as CustomEvent).detail }));
        }, 300);
        e.stopImmediatePropagation();
      }
    };
    window.addEventListener('ig:scroll-to-account', handler as EventListener);
    return () => window.removeEventListener('ig:scroll-to-account', handler as EventListener);
  }, [setActiveModule]);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      <WorkbenchSidebar
        activeModule={activeModule}
        onModuleChange={setActiveModule}
        visionExecutionMode={visionExecutionMode}
        visionExecutionModeSaving={visionExecutionModeSaving}
        onVisionExecutionModeChange={handleVisionExecutionModeChange}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        {!activeModule && (
          <WorkbenchHeader
            activeModule={activeModule}
            onBackToContent={() => setActiveModule(null)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            statusButtons={statusButtons}
          />
        )}

        {/* Main content */}
        <div className="flex-1 overflow-hidden">
          {/* Module-specific panels */}
          {activeModule === 'plan' && (
            <SeriesPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              selectedPostId={selectedPostId}
              posts={posts}
              onPostSelect={setSelectedPostId}
            />
          )}

          {activeModule === 'produce' && (
            <ProducePanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              posts={posts}
              selectedPostId={selectedPostId}
              onPostSelect={setSelectedPostId}
            />
          )}

          {activeModule === 'assets' && (
            <AssetsPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              posts={posts}
              selectedPostId={selectedPostId}
              onPostSelect={setSelectedPostId}
            />
          )}

          {activeModule === 'references' && (
            <ReferencesPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
            />
          )}

          {activeModule === 'access' && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Loading access controls...</div>
                </div>
              }
            >
              <AccessPanel
                workspaceId={workspaceId}
                apiUrl={baseApiUrl}
                browserProfile={{
                  browserSession,
                  profileName,
                  profilePathInput,
                  availableProfiles,
                  selectedProfileInfo,
                  setWorkspaceProfileName,
                  setProfilePathInput,
                  setWorkspaceProfilePathOverride,
                  checkBrowserSessionStatus,
                  loadProfiles,
                }}
                onOpenFollowingAnalyzer={handleOpenFollowingAnalyzer}
              />
            </Suspense>
          )}

          {activeModule === 'review' && (
            <ReviewPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
            />
          )}

          {activeModule === 'export' && (
            <ExportPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              selectedPostId={selectedPostId}
              posts={posts}
            />
          )}

          {activeModule === 'publish' && (
            <PublishPanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              selectedPostId={selectedPostId}
              posts={posts}
              onPostSelect={setSelectedPostId}
            />
          )}

          {activeModule === 'measure' && (
            <MeasurePanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
              selectedPostId={selectedPostId}
              posts={posts}
              onPostSelect={setSelectedPostId}
            />
          )}

          {activeModule === 'engage' && (
            <EngagePanel
              workspaceId={workspaceId}
              apiUrl={baseApiUrl}
            />
          )}

          {activeModule === 'discovery' && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Loading accounts...</div>
                </div>
              }
            >
              <AccountsPanel
                workspaceId={workspaceId}
                apiUrl={baseApiUrl}
                browserProfile={{
                  browserSession,
                  profileName,
                  profilePathInput,
                  availableProfiles,
                  selectedProfileInfo,
                  setWorkspaceProfileName,
                  setProfilePathInput,
                  setWorkspaceProfilePathOverride,
                  checkBrowserSessionStatus,
                  loadProfiles,
                }}
                onAccountSelect={(accountId) => {
                  setSelectedAccountId(accountId);
                }}
                recentRuns={recentRuns}
              />
            </Suspense>
          )}

          {activeModule === 'managed' && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Loading managed accounts...</div>
                </div>
              }
            >
              <ManagedAccountsPanel
                workspaceId={workspaceId}
                apiUrl={baseApiUrl}
                onOpenAccess={() => setActiveModule('access')}
                onOpenPublish={() => setActiveModule('publish')}
              />
            </Suspense>
          )}

          {/* Grid/Timeline/Kanban views (only shown when no module selected) */}
          {!activeModule && viewMode === 'grid' && (
            <>
              {postsLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Loading posts...</div>
                </div>
              ) : (
                <IGGridView
                  posts={posts}
                  selectedPostId={selectedPostId}
                  onPostSelect={setSelectedPostId}
                  statusFilter={statusFilter}
                  onRefresh={loadPosts}
                />
              )}
            </>
          )}

          {!activeModule && viewMode === 'timeline' && (
            <TimelineView
              posts={posts}
              selectedPostId={selectedPostId}
              onPostSelect={setSelectedPostId}
              statusFilter={statusFilter}
            />
          )}

          {!activeModule && viewMode === 'kanban' && (
            <KanbanView
              posts={posts}
              selectedPostId={selectedPostId}
              onPostSelect={setSelectedPostId}
              statusFilter={statusFilter}
              onStatusChange={async (postId, newStatus) => {
                await loadPosts();
              }}
            />
          )}

          {/* Placeholder for other modules */}
          {activeModule && !['access', 'discovery', 'managed', 'plan', 'produce', 'assets', 'references', 'review', 'export', 'publish', 'measure', 'engage'].includes(activeModule) && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-gray-500 dark:text-gray-400">
                <p className="text-lg mb-2">{WORKBENCH_MODULES.find(m => m.id === activeModule)?.label} Panel</p>
                <p className="text-sm">Coming in Phase 2/3</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <WorkbenchExecutionPanel
        workspaceId={workspaceId}
        apiUrl={baseApiUrl}
        activeBrowserProfile={{
          profileName,
          profilePath: browserSession.profilePath,
          pathSource: browserSession.pathSource,
          loggedIn: browserSession.loggedIn,
          sessionExpired: browserSession.sessionExpired,
          isChecking: browserSession.isChecking,
          igUsername: selectedProfileInfo?.ig_username || null,
          availableProfiles,
          onSelectProfile: handleSelectActiveProfile,
          onRefreshStatus: handleRefreshActiveProfile,
          onOpenAccess: () => setActiveModule('access'),
        }}
        selectedPostId={selectedPostId}
        getSelectedPost={getSelectedPost}
        posts={posts}
        statusFilter={statusFilter}
        runLogCounts={runLogCounts}
        targetsTotal={targetsTotal}
        recentRuns={recentRuns}
        recentGroups={recentGroups}
        isRunning={isRunning}
        error={error}
        onDismissError={() => setError(null)}
        onRunPlaybook={handleRunPlaybook}
        onRefreshRuns={loadRecentRuns}
      />

    </div>
  );
}
