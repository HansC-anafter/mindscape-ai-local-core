/**
 * Unified API URL utilities
 * All frontend code should use these functions to get the API URL instead of hardcoding ports
 */

/**
 * Get initial API URL (synchronous, for initialization)
 * Prioritizes env var, falls back to port config system default (8200)
 */
export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith('http')) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Use same-origin proxy (when frontend and backend share the same hostname)
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    return `${protocol}//${hostname}:8200`;
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
    const module = await import('../app/settings/utils/settingsApi') as any;
    const getDynamicApiUrl = module.getApiUrl;
    return await getDynamicApiUrl();
  } catch {
    return getApiBaseUrl();
  }
}


