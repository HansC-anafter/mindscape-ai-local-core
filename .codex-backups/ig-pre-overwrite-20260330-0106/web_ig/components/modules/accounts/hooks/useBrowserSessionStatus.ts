import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { BrowserSessionStatus, BrowserProfileInfo } from '../types';
import { fetchBrowserProfileStatus, fetchBrowserProfiles } from '../api';
import { getWorkspaceIGBrowserProfile, resolveWorkspaceIGUserDataDir, setWorkspaceIGBrowserProfile } from '../../../browserProfile';

const DEFAULT_PROFILE_PATH = '/app/data/ig-browser-profiles/default';

export function useBrowserSessionStatus(apiUrl: string, workspaceId: string) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const resolvedInitialPath = resolveWorkspaceIGUserDataDir(workspaceId) || DEFAULT_PROFILE_PATH;
  const [profileName, setProfileName] = useState<string>(() => {
    const p = getWorkspaceIGBrowserProfile(workspaceId);
    return p.profileName || 'default';
  });
  const [profilePathInput, setProfilePathInput] = useState<string>(() => {
    const p = getWorkspaceIGBrowserProfile(workspaceId);
    return p.profilePathOverride || resolvedInitialPath;
  });
  const [browserSession, setBrowserSession] = useState<BrowserSessionStatus>({
    hasProfile: false,
    loggedIn: false,
    hasSessionId: false,
    sessionExpired: false,
    sessionIdCookie: null,
    profilePath: resolvedInitialPath,
    pathSource: 'profile_name',
    sessionSource: 'none',
    storageStatePath: undefined,
    lastChecked: null,
    isChecking: false,
    message: '',
    igCookieCount: 0,
    igCookies: [],
  });

  const [availableProfiles, setAvailableProfiles] = useState<BrowserProfileInfo[]>([]);
  const profilesLoadedRef = useRef(false);

  const resolvedProfilePath = useMemo(() => {
    const v = (browserSession.profilePath || '').trim();
    return v || resolveWorkspaceIGUserDataDir(workspaceId) || DEFAULT_PROFILE_PATH;
  }, [browserSession.profilePath, workspaceId]);

  const selectedProfileInfo = useMemo(() => {
    const currentPath = (browserSession.profilePath || '').trim();
    if (!Array.isArray(availableProfiles) || availableProfiles.length === 0) {
      return null;
    }
    return (
      availableProfiles.find((profile) => profile.name === profileName) ||
      availableProfiles.find((profile) => (profile.path || '').trim() === currentPath) ||
      null
    );
  }, [availableProfiles, browserSession.profilePath, profileName]);

  useEffect(() => {
    setProfilePathInput(browserSession.profilePath || DEFAULT_PROFILE_PATH);
  }, [browserSession.profilePath]);

  useEffect(() => {
    // Keep in sync when workspace changes.
    const p = getWorkspaceIGBrowserProfile(workspaceId);
    setProfileName(p.profileName || 'default');
    const nextPath = p.profilePathOverride || resolveWorkspaceIGUserDataDir(workspaceId) || DEFAULT_PROFILE_PATH;
    setProfilePathInput(nextPath);
    setBrowserSession((prev) => ({
      ...prev,
      profilePath: nextPath,
      pathSource: p.profilePathOverride ? 'profile_path' : 'profile_name',
    }));
  }, [workspaceId]);

  const checkBrowserSessionStatus = useCallback(async (profilePathOverride?: string) => {
    setBrowserSession(prev => ({ ...prev, isChecking: true }));
    try {
      const profilePath = (profilePathOverride || profilePathInput || '').trim();
      const response = await fetchBrowserProfileStatus(client, {
        profilePath: profilePath || undefined,
        profileName: profilePath ? undefined : profileName,
      });
      if (response.ok) {
        const data = await response.json();
        setBrowserSession(prev => ({
          ...prev,
          hasProfile: data.exists === true,
          loggedIn: data.logged_in === true,
          hasSessionId: data.has_sessionid === true,
          sessionExpired: data.session_expired === true,
          sessionIdCookie: data.sessionid_cookie || null,
          profilePath: data.profile_path || profilePath || DEFAULT_PROFILE_PATH,
          pathSource: data.path_source || 'profile_name',
          sessionSource: data.session_source || 'none',
          storageStatePath: data.storage_state_path,
          lastChecked: new Date().toISOString(),
          isChecking: false,
          message: data.message || '',
          igCookieCount: data.ig_cookie_count || 0,
          igCookies: data.ig_cookies || [],
        }));
        if (data.profile_path) {
          setProfilePathInput(data.profile_path);
        }
      } else {
        setBrowserSession(prev => ({
          ...prev,
          hasProfile: false,
          loggedIn: false,
          hasSessionId: false,
          sessionExpired: false,
          sessionIdCookie: null,
          sessionSource: 'none',
          storageStatePath: undefined,
          lastChecked: new Date().toISOString(),
          isChecking: false,
          message: 'Failed to check status',
          igCookieCount: 0,
          igCookies: [],
        }));
      }
    } catch {
      setBrowserSession(prev => ({
        ...prev,
        hasProfile: false,
        loggedIn: false,
        hasSessionId: false,
        sessionExpired: false,
        sessionIdCookie: null,
        sessionSource: 'none',
        storageStatePath: undefined,
        lastChecked: new Date().toISOString(),
        isChecking: false,
        message: 'Error checking status',
        igCookieCount: 0,
        igCookies: [],
      }));
    }
  }, [client, profileName, profilePathInput]);

  const loadProfiles = useCallback(async () => {
    try {
      const res = await fetchBrowserProfiles(client);
      if (res.ok) {
        const data = await res.json();
        setAvailableProfiles(data.profiles || []);
      }
    } catch {
      // ignore
    }
  }, [client]);

  // Load profiles on mount
  useEffect(() => {
    if (!profilesLoadedRef.current) {
      profilesLoadedRef.current = true;
      void loadProfiles();
    }
  }, [loadProfiles]);

  const setWorkspaceProfileName = useCallback((nextName: string) => {
    const name = (nextName || '').trim() || 'default';
    setProfileName(name);
    setWorkspaceIGBrowserProfile(workspaceId, { profileName: name, profilePathOverride: undefined });
    const nextPath = resolveWorkspaceIGUserDataDir(workspaceId);
    setBrowserSession((prev) => ({
      ...prev,
      profilePath: nextPath,
      pathSource: 'profile_name',
    }));
    setProfilePathInput(nextPath);
  }, [workspaceId]);

  const setWorkspaceProfilePathOverride = useCallback((nextPath: string) => {
    const raw = (nextPath || '').trim();
    const p = getWorkspaceIGBrowserProfile(workspaceId);
    setWorkspaceIGBrowserProfile(workspaceId, { profileName: p.profileName || profileName, profilePathOverride: raw || undefined });
    const resolved = raw || resolveWorkspaceIGUserDataDir(workspaceId);
    setBrowserSession((prev) => ({
      ...prev,
      profilePath: resolved,
      pathSource: raw ? 'profile_path' : 'profile_name',
    }));
    setProfilePathInput(resolved);
  }, [workspaceId, profileName]);

  return {
    browserSession,
    profileName,
    setWorkspaceProfileName,
    profilePathInput,
    setProfilePathInput,
    setWorkspaceProfilePathOverride,
    resolvedProfilePath,
    checkBrowserSessionStatus,
    availableProfiles,
    selectedProfileInfo,
    loadProfiles,
  };
}
