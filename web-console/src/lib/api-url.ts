/**
 * Unified API URL utilities
 * All frontend code should use these functions to get the API URL instead of hardcoding ports
 */

function shouldUseSameOriginProxy(configuredUrl?: string): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  if (!configuredUrl || !configuredUrl.startsWith('http')) {
    return true;
  }

  try {
    const url = new URL(configuredUrl);
    return url.hostname === window.location.hostname;
  } catch {
    return true;
  }
}

/**
 * Get initial API URL (synchronous, for initialization)
 * Browser requests should prefer Next.js same-origin rewrites to avoid
 * fragile cross-port CORS behavior in forwarded/dev-proxy environments.
 */
export function getApiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window !== 'undefined') {
    if (shouldUseSameOriginProxy(configuredUrl)) {
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
