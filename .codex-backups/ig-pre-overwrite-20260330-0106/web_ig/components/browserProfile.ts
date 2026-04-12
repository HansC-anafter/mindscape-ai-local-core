export type IGWorkspaceBrowserProfile = {
  profileName: string;
  profilePathOverride?: string;
};

const STORAGE_KEY_PREFIX = 'ig.browser_profile:';
const DEFAULT_PROFILE_NAME = 'default';
const IG_BROWSER_PROFILES_ROOT = '/app/data/ig-browser-profiles';

function safeJsonParse<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function safeGetItem(key: string): string | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

function keyForWorkspace(workspaceId: string): string {
  return `${STORAGE_KEY_PREFIX}${workspaceId}`;
}

export function getWorkspaceIGBrowserProfile(workspaceId: string): IGWorkspaceBrowserProfile {
  const raw = safeGetItem(keyForWorkspace(workspaceId));
  const parsed = safeJsonParse<Partial<IGWorkspaceBrowserProfile>>(raw);
  const profileName = (parsed?.profileName || DEFAULT_PROFILE_NAME).toString().trim() || DEFAULT_PROFILE_NAME;
  const profilePathOverride = (parsed?.profilePathOverride || '').toString().trim() || undefined;
  return { profileName, profilePathOverride };
}

export function setWorkspaceIGBrowserProfile(workspaceId: string, next: IGWorkspaceBrowserProfile): void {
  const profileName = (next.profileName || DEFAULT_PROFILE_NAME).toString().trim() || DEFAULT_PROFILE_NAME;
  const profilePathOverride = (next.profilePathOverride || '').toString().trim() || undefined;
  safeSetItem(keyForWorkspace(workspaceId), JSON.stringify({ profileName, profilePathOverride }));
}

export function resolveWorkspaceIGUserDataDir(workspaceId: string): string {
  const { profileName, profilePathOverride } = getWorkspaceIGBrowserProfile(workspaceId);
  if (profilePathOverride) return profilePathOverride;
  return resolveIGBrowserProfilePath(profileName);
}

export function normalizeNewIGBrowserProfileName(raw: string): string {
  const trimmed = (raw || '').trim().toLowerCase();
  if (!trimmed) return '';
  return trimmed
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '');
}

export function resolveIGBrowserProfilePath(profileName: string): string {
  const name = (profileName || DEFAULT_PROFILE_NAME).toString().trim() || DEFAULT_PROFILE_NAME;
  return `${IG_BROWSER_PROFILES_ROOT}/${name}`;
}

function quoteShellArg(value: string): string {
  const raw = (value || '').toString();
  return `'${raw.replace(/'/g, `'\"'\"'`)}'`;
}

export function buildIGLoginHelperCommand(params: {
  profileName?: string;
  userDataDir?: string;
}): string {
  const userDataDir = (params.userDataDir || '').toString().trim();
  if (userDataDir) {
    return `cd mindscape-ai-local-core && python scripts/ig_login_helper.py --user-data-dir ${quoteShellArg(userDataDir)}`;
  }

  const profileName = normalizeNewIGBrowserProfileName(params.profileName || DEFAULT_PROFILE_NAME) || DEFAULT_PROFILE_NAME;
  return `cd mindscape-ai-local-core && python scripts/ig_login_helper.py --profile-name ${quoteShellArg(profileName)}`;
}

export function injectWorkspaceIGBrowserProfileInputs<T extends Record<string, any> | undefined>(
  workspaceId: string,
  inputs?: T
): Record<string, any> {
  const next: Record<string, any> = { ...(inputs || {}) };
  if (!next.workspace_id) {
    next.workspace_id = workspaceId;
  }
  const currentUserDataDir = (next.user_data_dir || '').toString().trim();
  if (!currentUserDataDir) {
    next.user_data_dir = resolveWorkspaceIGUserDataDir(workspaceId);
  }
  return next;
}
