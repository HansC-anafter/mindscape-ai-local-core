/**
 * Dashboard API client with authentication support
 */

import { getApiBaseUrl } from '@/lib/api-url';

const API_BASE = getApiBaseUrl();

/**
 * Error log throttling to prevent console spam
 * Only logs the same error once per time window
 */
class ErrorLogThrottle {
  private errorLogs: Map<string, number> = new Map();
  private readonly throttleWindowMs = 5000; // 5 seconds

  shouldLog(errorKey: string): boolean {
    const now = Date.now();
    const lastLogTime = this.errorLogs.get(errorKey);

    if (lastLogTime === undefined || now - lastLogTime > this.throttleWindowMs) {
      this.errorLogs.set(errorKey, now);
      return true;
    }

    return false;
  }

  clear(): void {
    this.errorLogs.clear();
  }
}

const errorLogThrottle = new ErrorLogThrottle();

/**
 * Get authentication token for Cloud mode
 * Returns null if no token is available or in Local mode
 *
 * NOTE: Token source in Cloud mode:
 * - Token should be provided by the authentication system (e.g., OAuth, SSO)
 * - Token is expected to be stored in localStorage or sessionStorage with key 'auth_token'
 * - If no token is found in Cloud mode, API requests will return 401 (R2)
 * - For development/testing: Manually set token in browser console:
 *   localStorage.setItem('auth_token', 'your-token-here')
 */
function getAuthToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  // Check if we're in Cloud mode (SITE_HUB_API_BASE is set)
  // In Cloud mode, token should be stored in localStorage or sessionStorage
  const token = localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token');
  return token;
}

/**
 * Check if running in Cloud mode
 */
function isCloudMode(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  // Check environment variable or localStorage flag
  return !!(
    process.env.NEXT_PUBLIC_SITE_HUB_API_BASE ||
    localStorage.getItem('cloud_mode') === 'true'
  );
}

/**
 * Build headers for API requests
 */
function buildHeaders(customHeaders?: HeadersInit): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...customHeaders,
  };

  // Always add Authorization header in Cloud mode (R2: Cloud mode requires token)
  // In Local mode, backend will use default_user, so no token needed
  if (isCloudMode()) {
    const token = getAuthToken();
    if (token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    } else {
      // In Cloud mode without token, backend will return 401 (R2)
      // We still make the request to let backend handle the error properly
      console.warn(
        'Cloud mode detected but no authentication token found. ' +
        'Request may fail with 401. ' +
        'To set token manually (dev only): localStorage.setItem("auth_token", "your-token")'
      );
    }
  }

  return headers;
}

/**
 * Handle API errors with proper error messages
 */
async function handleError(response: Response): Promise<never> {
  let errorMessage = `HTTP ${response.status}: ${response.statusText}`;

  try {
    const errorData = await response.json();
    errorMessage = errorData.detail || errorData.message || errorMessage;
  } catch {
    // If response is not JSON, use status text
  }

  const error = new Error(errorMessage) as Error & { status?: number };
  error.status = response.status;

  // Handle authentication errors
  if (response.status === 401) {
    error.message = 'Authentication required. Please log in.';
    // Optionally redirect to login page
    if (isCloudMode()) {
      console.error(
        'Cloud mode requires authentication token. ' +
        'Token should be provided by authentication system. ' +
        'For development: Check if token is set in localStorage/sessionStorage with key "auth_token"'
      );
    }
  } else if (response.status === 403) {
    error.message = 'Access denied. You do not have permission to access this resource.';
  }

  throw error;
}

/**
 * Make authenticated API request
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: buildHeaders(options.headers),
    });

    if (!response.ok) {
      await handleError(response);
    }

    return response.json();
  } catch (error) {
    // Handle network errors (e.g., ERR_INSUFFICIENT_RESOURCES, connection failures)
    const errorKey = `network_error:${url}`;
    const errorMessage =
      error instanceof Error ? error.message : 'Network request failed';

    // Throttle error logging to prevent console spam
    if (errorLogThrottle.shouldLog(errorKey)) {
      console.error(`API request failed: ${url}`, errorMessage);
    }

    // Create a user-friendly error
    const networkError = new Error('Failed to fetch') as Error & {
      status?: number;
      isNetworkError?: boolean;
    };
    networkError.status = 0;
    networkError.isNetworkError = true;

    throw networkError;
  }
}

/**
 * GET request
 */
export async function apiGet<T>(endpoint: string, options?: RequestInit): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'GET',
  });
}

/**
 * POST request
 */
export async function apiPost<T>(
  endpoint: string,
  data?: unknown,
  options?: RequestInit
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * DELETE request
 */
export async function apiDelete<T>(endpoint: string, options?: RequestInit): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'DELETE',
  });
}


