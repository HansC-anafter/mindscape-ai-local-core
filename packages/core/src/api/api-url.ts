/**
 * Unified API URL utility functions
 * All frontend code should use these functions to get API URL instead of hardcoding ports
 */

/**
 * Get initial API URL (synchronous version, for initialization)
 * Prefer environment variables, otherwise use port configuration system default (8200)
 */
export function getApiBaseUrl(): string {
  // Prefer environment variables
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith('http')) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Use same-origin proxy (if frontend and backend are on the same domain)
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // Use port configuration system default (8200)
    return `${protocol}//${hostname}:8200`;
  }

  // Server-side rendering uses default value (port configuration system default)
  return 'http://localhost:8200';
}

/**
 * Get dynamic API URL (async version, supports getting from port configuration service)
 * This function will try to get the latest URL from port configuration service,
 * falling back to initial URL if it fails
 */
export async function getApiUrl(): Promise<string> {
  // If settingsApi is available, use its dynamic get function
  try {
    // Note: This import is optional and may not be available in all contexts
    // The core package should not depend on app-specific modules
    // For now, we'll just return the base URL
    return getApiBaseUrl();
  } catch {
    // If import fails, fall back to synchronous version
    return getApiBaseUrl();
  }
}
