// Get initial API URL (avoids circular dependency)
const getInitialApiUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.startsWith('http')) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Use same-origin proxy (when frontend and backend share the same hostname)
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // Port config system default: 8200
    // Initial value; dynamically updated via port config API later
    return `${protocol}//${hostname}:8200`;
  }

  // SSR fallback (port config system default)
  return 'http://localhost:8200';
};

// Dynamically resolve API URL from port config service (scope-aware)
let apiUrlCache: string | null = null;
let apiUrlPromise: Promise<string> | null = null;
let lastValidationTime: number = 0;
let failedUrls: Set<string> = new Set(); // Track failed URLs to avoid retrying
const VALIDATION_INTERVAL = 30000; // Validate at most once per 30 seconds

const getApiUrl = async (forceRefresh: boolean = false): Promise<string> => {
  const now = Date.now();

  // Return cached URL if available and not force-refreshing
  if (apiUrlCache && !forceRefresh) {
    // Skip validation if cached URL previously failed
    if (failedUrls.has(apiUrlCache as string)) {
      const initialUrl = getInitialApiUrl();
      if (initialUrl !== apiUrlCache) {
        apiUrlCache = initialUrl;
        failedUrls.clear();
        return apiUrlCache;
      }
    }

    // Rate-limit validation: only re-validate after VALIDATION_INTERVAL
    if (now - lastValidationTime < VALIDATION_INTERVAL) {
      return apiUrlCache;
    }

    // Quick health check on cached URL
    try {
      const testController = new AbortController();
      const testTimeoutId = setTimeout(() => testController.abort(), 500);
      const testResponse = await fetch(`${apiUrlCache}/health`, {
        signal: testController.signal,
        method: 'GET', // Backend only supports GET, not HEAD
      });
      clearTimeout(testTimeoutId);
      lastValidationTime = now;
      if (testResponse.ok) {
        failedUrls.delete(apiUrlCache);
        return apiUrlCache;
      }
      failedUrls.add(apiUrlCache);
      apiUrlCache = null;
      apiUrlPromise = null;
    } catch (e) {
      lastValidationTime = now;
      if (apiUrlCache) {
        failedUrls.add(apiUrlCache);
        console.warn(`Cached API URL (${apiUrlCache}) unreachable, clearing cache`);
      }
      apiUrlCache = null;
      apiUrlPromise = null;
    }
  }

  // Wait for in-flight request if available
  if (apiUrlPromise && !forceRefresh) {
    return apiUrlPromise;
  }

  // First load or force refresh
  apiUrlPromise = (async () => {
    const initialUrl = getInitialApiUrl();

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
              failedUrls.delete(backendUrl);
              return apiUrlCache;
            } else {
              failedUrls.add(backendUrl);
            }
          } catch (e) {
            failedUrls.add(backendUrl);
            console.warn(`Configured API URL (${backendUrl}) unreachable, falling back to initial URL (${initialUrl})`);
          }
        } else {
          apiUrlCache = backendUrl;
          failedUrls.delete(backendUrl);
          return apiUrlCache;
        }
      }
    } catch (error) {
      // Port config service unavailable; fall back to initial URL
      console.warn('Cannot fetch API URL from config service, using initial URL:', error);
    }

    // Fallback to initial URL
    const fallbackUrl = getInitialApiUrl();
    apiUrlCache = fallbackUrl;
    failedUrls.delete(fallbackUrl);
    lastValidationTime = now;
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
  detail?: string;
  message?: string;
}

const parseError = async (response: Response): Promise<string> => {
  try {
    const errorData: ApiError = await response.json();
    return errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`;
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
