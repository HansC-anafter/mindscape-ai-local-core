import { shouldUseSameOriginProxyForBrowser } from '../../../lib/api-origin';

// Get initial API URL (avoids circular dependency)
const getInitialApiUrl = (): string => {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;

  if (typeof window !== 'undefined') {
    if (shouldUseSameOriginProxyForBrowser(configuredUrl)) {
      return '';
    }
    return configuredUrl as string;
  }

  if (configuredUrl && configuredUrl.startsWith('http')) {
    return configuredUrl;
  }

  // SSR fallback (port config system default)
  return 'http://localhost:8200';
};

// Dynamically resolve API URL from port config service (scope-aware)
let apiUrlCache: string | null = null;
let apiUrlPromise: Promise<string> | null = null;
let lastValidationTime: number = 0;
let isValidating: boolean = false; // Lock to prevent concurrent validation races
const VALIDATION_INTERVAL = 60000; // Validate at most once per 60 seconds (was 30s)

const getApiUrl = async (forceRefresh: boolean = false): Promise<string> => {
  const now = Date.now();

  // Return cached URL if available and not force-refreshing
  if (apiUrlCache !== null && !forceRefresh) {
    // Rate-limit validation: only re-validate after VALIDATION_INTERVAL
    if (now - lastValidationTime < VALIDATION_INTERVAL) {
      return apiUrlCache;
    }

    // Prevent concurrent validation — if another call is already validating, just use cache
    if (isValidating) {
      return apiUrlCache;
    }

    // Quick health check on cached URL (skip if using same-origin proxy)
    if (apiUrlCache !== '') {
      isValidating = true;
      try {
        const testController = new AbortController();
        const testTimeoutId = setTimeout(() => testController.abort(), 500);
        const testResponse = await fetch(`${apiUrlCache}/health`, {
          signal: testController.signal,
          method: 'GET',
        });
        clearTimeout(testTimeoutId);
        lastValidationTime = now;
        isValidating = false;
        if (testResponse.ok) {
          return apiUrlCache;
        }
        // Health check failed but DON'T clear cache — keep using it
        // The actual API calls will fail on their own if the backend is truly down
      } catch (e) {
        // Health check timed out — DON'T clear cache, just update timestamp
        lastValidationTime = now;
        isValidating = false;
      }
      return apiUrlCache;
    } else {
      // Same-origin proxy: no health check needed
      lastValidationTime = now;
      return apiUrlCache;
    }
  }

  // Wait for in-flight request if available
  if (apiUrlPromise && !forceRefresh) {
    return apiUrlPromise;
  }

  // First load or force refresh
  apiUrlPromise = (async () => {
    const initialUrl = getInitialApiUrl();

    // If using same-origin proxy (remote access), skip all port config resolution
    if (initialUrl === '') {
      apiUrlCache = '';
      lastValidationTime = Date.now();
      return apiUrlCache;
    }

    try {
      // Resolve current scope (priority: global state > localStorage > env vars)
      let cluster: string | undefined;
      let environment: string | undefined;
      let site: string | undefined;

      // Method 1: Global state manager
      if (typeof window !== 'undefined' && (window as any).__PORT_CONFIG_SCOPE__) {
        const scope = (window as any).__PORT_CONFIG_SCOPE__;
        cluster = scope.cluster;
        environment = scope.environment;
        site = scope.site;
      }

      // Method 2: localStorage (persisted from settings UI)
      if (typeof window !== 'undefined' && !cluster && !environment && !site) {
        try {
          const savedScope = localStorage.getItem('port_config_scope');
          if (savedScope) {
            const scope = JSON.parse(savedScope);
            cluster = scope.cluster || undefined;
            environment = scope.environment || undefined;
            site = scope.site || undefined;
          }
        } catch (e) {
          // Ignore parse errors
        }
      }

      // Method 3: Fall back to env vars
      if (!cluster && !environment && !site) {
        cluster = process.env.NEXT_PUBLIC_CLUSTER;
        environment = process.env.NEXT_PUBLIC_ENVIRONMENT;
        site = process.env.NEXT_PUBLIC_SITE;
      }

      // Normalize: treat "default" as unset (use global config)
      if (environment === 'default') {
        environment = undefined;
      }

      // Build scoped query params
      const params = new URLSearchParams();
      if (cluster) params.append('cluster', cluster);
      if (environment) params.append('environment', environment);
      if (site) params.append('site', site);

      const url = `${initialUrl}/api/v1/system-settings/ports/urls${params.toString() ? '?' + params.toString() : ''}`;

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);

      const response = await fetch(url, {
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const urls: { backend_api_url: string } = await response.json();
        const backendUrl = urls.backend_api_url;
        // Verify the returned URL is reachable if different from initial
        if (backendUrl !== initialUrl) {
          try {
            const testController = new AbortController();
            const testTimeoutId = setTimeout(() => testController.abort(), 1000);
            const testResponse = await fetch(`${backendUrl}/health`, {
              signal: testController.signal,
            });
            clearTimeout(testTimeoutId);
            if (testResponse.ok) {
              apiUrlCache = backendUrl;
              lastValidationTime = Date.now();
              return apiUrlCache;
            }
          } catch (e) {
            console.warn(`Configured API URL (${backendUrl}) unreachable, falling back to initial URL (${initialUrl})`);
          }
        } else {
          apiUrlCache = backendUrl;
          lastValidationTime = Date.now();
          return apiUrlCache;
        }
      }
    } catch (error) {
      // Port config service unavailable; fall back silently
    }

    // Fallback to initial URL
    apiUrlCache = initialUrl;
    lastValidationTime = Date.now();
    return apiUrlCache;
  })();

  return apiUrlPromise;
};

// Synchronous version (returns initial URL, for initialization)
const getApiUrlSync = (): string => {
  return getInitialApiUrl();
};

export const getInitialApiUrlForClient = (): string => {
  return getInitialApiUrl();
};

interface ApiError {
  detail?: unknown;
  message?: string;
  error?: string;
  hint?: string;
  summary?: string;
  required_confirmation?: string;
}

const formatApiError = (payload: unknown): string | null => {
  if (payload == null) {
    return null;
  }
  if (typeof payload === 'string') {
    return payload;
  }
  if (typeof payload !== 'object') {
    return String(payload);
  }

  const data = payload as Record<string, unknown>;
  const parts = [
    typeof data.message === 'string' ? data.message.trim() : '',
    typeof data.detail === 'string' ? data.detail.trim() : '',
    typeof data.summary === 'string' ? data.summary.trim() : '',
    typeof data.hint === 'string' ? data.hint.trim() : '',
    typeof data.required_confirmation === 'string'
      ? `Required confirmation: ${data.required_confirmation}`
      : '',
  ].filter(Boolean);

  if (parts.length > 0) {
    return parts.join('\n');
  }

  try {
    return JSON.stringify(payload);
  } catch {
    return String(payload);
  }
};

const parseError = async (response: Response): Promise<string> => {
  try {
    const errorData: ApiError = await response.json();
    return (
      formatApiError(errorData.detail ?? errorData) ||
      formatApiError(errorData.message) ||
      `HTTP ${response.status}: ${response.statusText}`
    );
  } catch {
    const text = await response.text();
    return text || `HTTP ${response.status}: ${response.statusText}`;
  }
};

export const settingsApi = {
  baseURL: getApiUrlSync(),
  get: async <T>(endpoint: string, options?: { silent?: boolean }): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;

    try {
      const response = await fetch(url);

      if (!response.ok) {
        // For expected errors (501, 404) with silent flag, return empty/default data instead of throwing
        if (options?.silent && (response.status === 501 || response.status === 404)) {
          if (endpoint.includes('/connections') || endpoint.includes('/capability-packs') || endpoint.includes('/capability-suites') || endpoint.includes('/playbooks')) {
            return [] as T;
          }
          return {} as T;
        }

        const errorMessage = await parseError(response);
        throw new Error(errorMessage);
      }

      return response.json();
    } catch (error) {
      if (options?.silent) {
        if (endpoint.includes('/connections') || endpoint.includes('/capability-packs') || endpoint.includes('/capability-suites') || endpoint.includes('/playbooks')) {
          return [] as T;
        }
        return {} as T;
      }
      throw error;
    }
  },

  put: async <T>(endpoint: string, data: unknown): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  patch: async <T>(endpoint: string, data: unknown): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  post: async <T>(endpoint: string, data?: unknown): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const options: RequestInit = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    const response = await fetch(url, options);

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  postFormData: async <T>(endpoint: string, formData: FormData): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },

  delete: async <T>(endpoint: string): Promise<T> => {
    const apiUrl = await getApiUrl();
    const url = endpoint.startsWith('http') ? endpoint : `${apiUrl}${endpoint}`;
    const response = await fetch(url, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      const errorMessage = await parseError(response);
      throw new Error(errorMessage);
    }

    return response.json();
  },
};
