/**
 * Unified API URL utilities
 * All frontend code should use these functions to get the API URL instead of hardcoding ports
 */

import {
  normalizeBrowserReachableUrl,
  shouldUseSameOriginProxyForBrowser,
} from './api-origin';

/**
 * Get initial API URL (synchronous, for initialization)
 * Browser requests prefer the configured backend URL when it is directly
 * reachable (for example localhost:8200 in local-core dev/runtime), and fall
 * back to the same-origin proxy only for internal/non-browser hosts.
 */
export function getApiBaseUrl(): string {
  const configuredUrl = normalizeBrowserReachableUrl(process.env.NEXT_PUBLIC_API_URL);

  if (typeof window !== 'undefined') {
    if (shouldUseSameOriginProxyForBrowser(configuredUrl)) {
      return '';
    }
    return configuredUrl as string;
  }

  if (configuredUrl && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  // SSR fallback
  return 'http://localhost:8200';
}

/**
 * Get dynamic API URL (async, supports fetching from port config service)
 * Attempts to query port config service for latest URL, falls back to initial URL on failure
 */
export async function getApiUrl(): Promise<string> {
  try {
    const settingsApiModule = await import('../app/settings/utils/settingsApi') as any;
    const getDynamicApiUrl = settingsApiModule.getApiUrl;
    return await getDynamicApiUrl();
  } catch {
    return getApiBaseUrl();
  }
}
