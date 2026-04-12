'use client';

import React, { useCallback, useState } from 'react';
import { KeyRound, Shield } from 'lucide-react';

import type { BrowserProfileController } from './accounts/types';
import { useConnectedAccounts } from './accounts/hooks/useConnectedAccounts';
import { SessionTab } from './accounts/components/SessionTab';
import { OAuthTab } from './accounts/components/OAuthTab';
import { resolveWorkspaceIGUserDataDir } from '../browserProfile';

type AccessTabKey = 'profiles' | 'oauth';

interface AccessPanelProps {
  workspaceId: string;
  apiUrl: string;
  browserProfile: BrowserProfileController;
  onOpenFollowingAnalyzer: () => void;
}

export default function AccessPanel(props: AccessPanelProps) {
  const {
    workspaceId,
    apiUrl,
    browserProfile,
    onOpenFollowingAnalyzer,
  } = props;
  const [activeTab, setActiveTab] = useState<AccessTabKey>('profiles');
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const { connectedAccounts, refresh: refreshConnectedAccounts } = useConnectedAccounts({ apiUrl, workspaceId });
  const {
    browserSession,
    profileName,
    setWorkspaceProfileName,
    profilePathInput,
    setProfilePathInput,
    setWorkspaceProfilePathOverride,
    checkBrowserSessionStatus,
    availableProfiles,
    loadProfiles,
  } = browserProfile;

  const refreshAccessState = useCallback(async () => {
    await loadProfiles();
    await refreshConnectedAccounts();
    await checkBrowserSessionStatus(
      (browserSession.profilePath || '').trim() || resolveWorkspaceIGUserDataDir(workspaceId)
    );
  }, [
    browserSession.profilePath,
    checkBrowserSessionStatus,
    loadProfiles,
    refreshConnectedAccounts,
    workspaceId,
  ]);

  const handleCheckStatus = useCallback((profilePathOverride?: string) => {
    const resolvedPath = (profilePathOverride || '').trim() || resolveWorkspaceIGUserDataDir(workspaceId);
    void checkBrowserSessionStatus(resolvedPath);
  }, [checkBrowserSessionStatus, workspaceId]);

  return (
    <div className="h-full flex flex-col p-3">
      <div className="mb-4 rounded-xl border border-gray-200 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Access Control</h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Manage browser profiles and OAuth bindings that power new IG runs across this workspace.
            </p>
          </div>
          <div className="rounded-lg bg-violet-50 px-3 py-2 text-xs text-violet-700 dark:bg-violet-900/30 dark:text-violet-300">
            Active profile applies to new browser tasks
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2 border-b border-gray-200 pb-1 dark:border-gray-700">
          <button
            type="button"
            onClick={() => setActiveTab('profiles')}
            className={`inline-flex items-center gap-2 rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium ${
              activeTab === 'profiles'
                ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
          >
            <KeyRound className="h-4 w-4" />
            Browser Profiles
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('oauth')}
            className={`inline-flex items-center gap-2 rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium ${
              activeTab === 'oauth'
                ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
            }`}
          >
            <Shield className="h-4 w-4" />
            OAuth Connections
          </button>
        </div>
      </div>

      {activeTab === 'profiles' ? (
        <SessionTab
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          onCaptureComplete={() => {
            void refreshAccessState();
          }}
          onOpenFollowingAnalyzer={onOpenFollowingAnalyzer}
          profileName={profileName}
          onProfileNameChange={setWorkspaceProfileName}
          profilePathInput={profilePathInput}
          onProfilePathInputChange={setProfilePathInput}
          onSetProfilePathOverride={setWorkspaceProfilePathOverride}
          onCheckStatus={handleCheckStatus}
          browserSession={browserSession}
          copiedCommand={copiedCommand}
          onCopiedCommandChange={setCopiedCommand}
          availableProfiles={availableProfiles}
          onRefreshProfiles={refreshAccessState}
        />
      ) : (
        <OAuthTab
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          connectedAccounts={connectedAccounts}
          onRefreshAccounts={() => {
            void refreshConnectedAccounts();
          }}
        />
      )}
    </div>
  );
}
