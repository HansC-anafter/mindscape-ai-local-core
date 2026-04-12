import React, { useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Plus,
  RefreshCw,
  Terminal,
  Users,
  XCircle,
  Zap,
} from 'lucide-react';

import type { BrowserSessionStatus, BrowserProfileInfo } from '../types';
import IGDirectCapture from '../../IGDirectCapture';
import {
  buildIGLoginHelperCommand,
  normalizeNewIGBrowserProfileName,
  resolveIGBrowserProfilePath,
} from '../../../browserProfile';

export type SessionTabProps = {
  workspaceId: string;
  apiUrl: string;
  onCaptureComplete: () => void;
  onOpenFollowingAnalyzer: () => void;

  profileName: string;
  onProfileNameChange: (value: string) => void;

  profilePathInput: string;
  onProfilePathInputChange: (value: string) => void;
  onSetProfilePathOverride: (value: string) => void;
  onCheckStatus: (profilePathOverride?: string) => void;

  browserSession: BrowserSessionStatus;
  copiedCommand: string | null;
  onCopiedCommandChange: (value: string | null) => void;

  availableProfiles: BrowserProfileInfo[];
  onRefreshProfiles: () => Promise<void>;
};

export function SessionTab(props: SessionTabProps) {
  const {
    workspaceId,
    apiUrl,
    onCaptureComplete,
    onOpenFollowingAnalyzer,
    profileName,
    onProfileNameChange,
    profilePathInput,
    onProfilePathInputChange,
    onSetProfilePathOverride,
    onCheckStatus,
    browserSession,
    copiedCommand,
    onCopiedCommandChange,
    availableProfiles,
    onRefreshProfiles,
  } = props;
  const [newAccessInput, setNewAccessInput] = useState('');
  const normalizedNewAccessName = useMemo(
    () => normalizeNewIGBrowserProfileName(newAccessInput),
    [newAccessInput]
  );
  const currentProfileExists = availableProfiles.some((profile) => profile.name === profileName);
  const resolvedNamedProfilePath = resolveIGBrowserProfilePath(profileName);
  const usesCustomPathOverride = (browserSession.profilePath || '').trim() !== resolvedNamedProfilePath;
  const loginCommand = useMemo(() => buildIGLoginHelperCommand({
    profileName,
    userDataDir: usesCustomPathOverride ? browserSession.profilePath : undefined,
  }), [browserSession.profilePath, profileName, usesCustomPathOverride]);

  const handleAddAccess = () => {
    const nextProfileName = normalizeNewIGBrowserProfileName(newAccessInput);
    if (!nextProfileName) return;
    onProfileNameChange(nextProfileName);
    onCheckStatus(resolveIGBrowserProfilePath(nextProfileName));
    setNewAccessInput('');
  };

  return (
    <div className="flex-1 overflow-y-auto pb-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 border border-purple-200 dark:border-purple-800 rounded-lg p-3 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <h3 className="font-semibold text-purple-900 dark:text-purple-100">
              Quick Capture
            </h3>
            <span className="px-2 py-0.5 text-xs bg-purple-100 dark:bg-purple-800 text-purple-700 dark:text-purple-300 rounded">
              Recommended
            </span>
          </div>
          <p className="text-sm text-purple-700 dark:text-purple-300 mb-4">
            Use your existing Instagram login. No setup required.
          </p>
          <div className="flex-1">
            <IGDirectCapture
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              onCaptureComplete={onCaptureComplete}
            />
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-gray-600 dark:text-gray-400" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                Backend Automation
              </h3>
            </div>
            <button
              onClick={() => onCheckStatus(profilePathInput)}
              disabled={browserSession.isChecking}
              className="text-xs text-blue-600 hover:underline flex items-center gap-1"
            >
              <RefreshCw className={`w-3 h-3 ${browserSession.isChecking ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          <div className="mb-3 space-y-2">
            <label className="text-xs text-gray-600 dark:text-gray-400">IG Browser Profile</label>

            <div className="grid grid-cols-1 gap-2">
              <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50/70 p-3 dark:border-blue-800 dark:bg-blue-900/20">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-blue-900 dark:text-blue-100">
                      Add New Access
                    </div>
                    <p className="mt-1 text-[11px] text-blue-700 dark:text-blue-300">
                      Create another browser profile slot for a different Instagram login. After adding it,
                      run the login helper and close the browser to persist the new session.
                    </p>
                  </div>
                  <Plus className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <input
                    type="text"
                    value={newAccessInput}
                    onChange={(e) => setNewAccessInput(e.target.value)}
                    className="flex-1 px-2 py-1.5 text-xs border rounded dark:bg-gray-800 dark:border-gray-700 bg-white"
                    placeholder="client-a"
                    aria-label="New IG access profile name"
                  />
                  <button
                    onClick={handleAddAccess}
                    disabled={!normalizedNewAccessName}
                    className="px-2.5 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    Add
                  </button>
                </div>
                {normalizedNewAccessName && (
                  <div className="mt-2 text-[11px] text-blue-700 dark:text-blue-300">
                    New access path: <span className="font-mono">{resolveIGBrowserProfilePath(normalizedNewAccessName)}</span>
                  </div>
                )}
              </div>

              {/* Profile selector dropdown */}
              {availableProfiles.length > 0 ? (
                <div className="flex items-center gap-2">
                  <select
                    value={profileName}
                    onChange={(e) => {
                      onProfileNameChange(e.target.value);
                      onCheckStatus();
                    }}
                    className="flex-1 px-2 py-1.5 text-xs border rounded dark:bg-gray-800 dark:border-gray-700 bg-white appearance-none cursor-pointer"
                    aria-label="Select IG browser profile"
                  >
                    {availableProfiles.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name}
                        {p.logged_in ? ' ✓' : p.session_expired ? ' ⚠ expired' : ''}
                        {p.ig_username ? ` @${p.ig_username}` : p.ig_user_id ? ` (uid: ${p.ig_user_id})` : ''}
                      </option>
                    ))}
                    {!availableProfiles.some((p) => p.name === profileName) && (
                      <option value={profileName}>Create access: {profileName}</option>
                    )}
                  </select>
                  <button
                    onClick={() => {
                      void onRefreshProfiles();
                      onCheckStatus();
                    }}
                    disabled={browserSession.isChecking}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
                    title="Refresh profile list and status"
                  >
                    Check
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={profileName}
                    onChange={(e) => onProfileNameChange(e.target.value)}
                    className="flex-1 px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                    placeholder="default"
                    aria-label="IG browser profile name"
                  />
                  <button
                    onClick={() => onCheckStatus()}
                    disabled={browserSession.isChecking}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
                    title="Check profile status by profile_name"
                  >
                    Check
                  </button>
                </div>
              )}

              {/* Profile status pills */}
              {availableProfiles.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {availableProfiles.map((p) => (
                    <button
                      key={p.name}
                      onClick={() => {
                        onProfileNameChange(p.name);
                        onCheckStatus();
                      }}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full border transition-colors ${p.name === profileName
                        ? 'border-blue-400 dark:border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium'
                        : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                        }`}
                      title={`Switch to profile: ${p.name}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${p.logged_in ? 'bg-green-500' : p.session_expired ? 'bg-amber-500' : 'bg-gray-400'
                        }`} />
                      {p.name}
                      {p.ig_username ? ` · @${p.ig_username}` : p.ig_user_id ? ` · ${p.ig_user_id}` : ''}
                    </button>
                  ))}
                </div>
              )}

              <div className="text-[11px] text-gray-500 dark:text-gray-500">
                Resolved path: <span className="font-mono">{browserSession.profilePath}</span>
              </div>

              {!browserSession.hasProfile && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                  <div className="font-semibold">
                    {currentProfileExists ? 'This access has no saved session yet' : `Create access: ${profileName}`}
                  </div>
                  <div className="mt-1">
                    Run the login helper for this access, log in or switch account in the opened browser, then close it.
                    The new session will be saved to <span className="font-mono">{browserSession.profilePath || resolvedNamedProfilePath}</span>.
                  </div>
                </div>
              )}

              <details className="text-sm">
                <summary className="cursor-pointer text-xs text-gray-600 dark:text-gray-300">
                  Advanced: Override profile path
                </summary>
                <div className="mt-2 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={profilePathInput}
                      onChange={(e) => onProfilePathInputChange(e.target.value)}
                      className="flex-1 px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                      placeholder="/app/data/ig-browser-profiles/default"
                      aria-label="IG browser profile path override"
                    />
                    <button
                      onClick={() => {
                        onSetProfilePathOverride(profilePathInput);
                        onCheckStatus(profilePathInput);
                      }}
                      disabled={browserSession.isChecking}
                      className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
                      title="Persist override and check status"
                    >
                      Use
                    </button>
                  </div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-500">
                    Current: {browserSession.profilePath} ({browserSession.pathSource || 'profile_name'})
                  </div>
                </div>
              </details>
            </div>
          </div>

          <div className={`rounded-lg p-3 mb-3 ${browserSession.loggedIn
            ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
            : browserSession.sessionExpired
              ? 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'
              : browserSession.hasProfile
                ? 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            }`}>
            <div className="flex items-center gap-2 mb-2">
              {browserSession.loggedIn ? (
                <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
              ) : browserSession.sessionExpired ? (
                <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              ) : browserSession.hasProfile ? (
                <AlertCircle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
              )}
              <span className={`font-semibold text-sm ${browserSession.loggedIn
                ? 'text-green-700 dark:text-green-300'
                : browserSession.sessionExpired
                  ? 'text-amber-700 dark:text-amber-300'
                  : browserSession.hasProfile
                    ? 'text-yellow-700 dark:text-yellow-300'
                    : 'text-red-700 dark:text-red-300'
                }`}>
                {browserSession.loggedIn
                  ? 'Logged In'
                  : browserSession.sessionExpired
                    ? 'Session Expired'
                    : browserSession.hasProfile
                      ? 'Profile Exists - Not Logged In'
                      : 'No Profile'}
              </span>
            </div>
            <div className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
              <p>
                <strong>sessionid:</strong>{' '}
                {browserSession.hasSessionId
                  ? browserSession.sessionExpired
                    ? 'Expired'
                    : 'Present'
                  : 'Missing'}
              </p>
              <p><strong>IG Cookies:</strong> {browserSession.igCookieCount} found</p>
              {browserSession.igCookies.length > 0 && (
                <p className="text-gray-500 truncate" title={browserSession.igCookies.map(c => c.name).join(', ')}>
                  ({browserSession.igCookies.map(c => c.name).join(', ')})
                </p>
              )}
              {browserSession.storageStatePath && (
                <p className="text-gray-500 truncate">
                  storage_state: {browserSession.storageStatePath}
                </p>
              )}
              <p className="text-gray-500 mt-1">{browserSession.message}</p>
            </div>
          </div>

          <div className="flex-1 space-y-3">
            <button
              onClick={onOpenFollowingAnalyzer}
              disabled={!browserSession.loggedIn}
              className={`w-full px-3 py-2 text-sm rounded flex items-center justify-center gap-2 ${browserSession.loggedIn
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-500 cursor-not-allowed'
                }`}
            >
              <Users className="w-4 h-4" />
              {browserSession.loggedIn ? 'Analyze Following List' : 'Login Required'}
            </button>

            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
              <p>Auto-scroll through following list</p>
              <p>Visit each account for details</p>
              <p>Extract bio, followers, posts</p>
            </div>

            <details className="text-sm" open={!browserSession.loggedIn}>
              <summary className="cursor-pointer text-blue-600 dark:text-blue-400 hover:underline font-medium">
                {browserSession.loggedIn ? 'Re-login Instructions' : 'Login Instructions'}
              </summary>
              <div className="mt-3 space-y-3 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                <div>
                  <p className="text-gray-700 dark:text-gray-300 mb-2 text-xs">
                    Run on your local machine for this access:
                  </p>
                  <div className="relative">
                    <pre className="bg-gray-100 dark:bg-gray-900 rounded p-2 text-xs font-mono overflow-x-auto">
                      <code>{loginCommand}</code>
                    </pre>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(loginCommand);
                        onCopiedCommandChange('step1');
                        setTimeout(() => onCopiedCommandChange(null), 2000);
                      }}
                      className="absolute top-1 right-1 p-1 bg-gray-200 dark:bg-gray-700 rounded"
                    >
                      {copiedCommand === 'step1' ? (
                        <CheckCircle2 className="w-3 h-3 text-green-600" />
                      ) : (
                        <Copy className="w-3 h-3 text-gray-600 dark:text-gray-400" />
                      )}
                    </button>
                  </div>
                </div>
                <p className="text-gray-600 dark:text-gray-400 text-xs">
                  Browser opens → Log in or switch account → Close window → Click Refresh above
                </p>
                <p className="text-gray-600 dark:text-gray-400 text-xs">
                  Target session path: <span className="font-mono">{browserSession.profilePath || resolvedNamedProfilePath}</span>
                </p>
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>
  );
}
