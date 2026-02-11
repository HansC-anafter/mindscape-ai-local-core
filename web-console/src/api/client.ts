/**
 * MindscapeAPIClient - Unified API client for Local and Cloud environments
 *
 * Features:
 * - Automatic Local/Cloud URL resolution
 * - Authentication headers (JWT tokens, tenant/group IDs)
 * - GET request deduplication (same URL → single inflight request)
 * - Retry with exponential backoff for 429/503
 *
 * Playbook components should use this client instead of directly calling fetch.
 */

import { ExecutionContext } from '@/types/execution-context';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_RETRIES = 3;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

// ---------------------------------------------------------------------------
// MindscapeAPIClient
// ---------------------------------------------------------------------------

export class MindscapeAPIClient {
  private baseUrl: string;
  private context: ExecutionContext;

  /** GET dedup: key → inflight promise */
  private inflightGets: Map<string, Promise<Response>> = new Map();

  constructor(context: ExecutionContext) {
    this.context = context;

    if (context.tags?.mode === 'cloud') {
      this.baseUrl =
        process.env.NEXT_PUBLIC_CLOUD_API_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        'http://localhost:8500';
    } else {
      this.baseUrl =
        process.env.NEXT_PUBLIC_API_URL ||
        'http://localhost:8200';
    }
  }

  /**
   * Create a client from a base URL string.
   * Use this in pack components that receive `apiUrl` as a prop.
   *
   * @example
   * ```tsx
   * const client = MindscapeAPIClient.fromBaseUrl(apiUrl);
   * const res = await client.get('/api/v1/workspaces/...');
   * ```
   */
  static fromBaseUrl(baseUrl: string): MindscapeAPIClient {
    const ctx: ExecutionContext = {
      actor_id: 'local-user',
      workspace_id: '',
    };
    const instance = new MindscapeAPIClient(ctx);
    instance.baseUrl = baseUrl;
    return instance;
  }

  // -------------------------------------------------------------------------
  // Auth
  // -------------------------------------------------------------------------

  /**
   * Get authentication token for Cloud mode.
   * Returns null if no token is available or in Local mode.
   */
  private getAuthToken(): string | null {
    return this.context.authToken || null;
  }

  // -------------------------------------------------------------------------
  // Headers
  // -------------------------------------------------------------------------

  private buildHeaders(customHeaders?: HeadersInit): HeadersInit {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Merge custom headers
    if (customHeaders) {
      this.mergeHeaders(headers, customHeaders);
    }

    // Cloud-specific headers
    if (this.context.tags?.mode === 'cloud') {
      const token = this.getAuthToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (this.context.tags.tenant_id) headers['X-Tenant-ID'] = this.context.tags.tenant_id;
      if (this.context.tags.group_id) headers['X-Group-ID'] = this.context.tags.group_id;
    }

    return headers;
  }

  /**
   * Build headers without Content-Type (for FormData — browser sets boundary)
   */
  private buildHeadersWithoutContentType(customHeaders?: HeadersInit): HeadersInit {
    const headers: Record<string, string> = {};

    if (customHeaders) {
      this.mergeHeaders(headers, customHeaders, /* skipContentType */ true);
    }

    if (this.context.tags?.mode === 'cloud') {
      const token = this.getAuthToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
      if (this.context.tags.tenant_id) headers['X-Tenant-ID'] = this.context.tags.tenant_id;
      if (this.context.tags.group_id) headers['X-Group-ID'] = this.context.tags.group_id;
    }

    return headers;
  }

  private mergeHeaders(
    target: Record<string, string>,
    source: HeadersInit,
    skipContentType = false
  ): void {
    if (source instanceof Headers) {
      source.forEach((value, key) => {
        if (!skipContentType || key.toLowerCase() !== 'content-type') {
          target[key] = value;
        }
      });
    } else if (Array.isArray(source)) {
      source.forEach(([key, value]) => {
        if (!skipContentType || key.toLowerCase() !== 'content-type') {
          target[key] = value;
        }
      });
    } else {
      Object.entries(source).forEach(([key, value]) => {
        if (!skipContentType || key.toLowerCase() !== 'content-type') {
          target[key] = value as string;
        }
      });
    }
  }

  // -------------------------------------------------------------------------
  // Retry with Exponential Backoff
  // -------------------------------------------------------------------------

  /**
   * Fetch with automatic retry on 429 (Too Many Requests) and 503 (Service Unavailable).
   * Uses exponential backoff: 1s → 2s → 4s, capped at 30s.
   */
  private async fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
    let attempt = 0;
    while (true) {
      const res = await fetch(url, init);
      if ((res.status === 429 || res.status === 503) && attempt < MAX_RETRIES) {
        const delay = Math.min(BACKOFF_BASE_MS * Math.pow(2, attempt), BACKOFF_CAP_MS);
        await new Promise(r => setTimeout(r, delay));
        attempt++;
        continue;
      }
      return res;
    }
  }

  // -------------------------------------------------------------------------
  // GET Dedup
  // -------------------------------------------------------------------------

  private buildDedupKey(endpoint: string): string {
    const tenantId = this.context.tags?.tenant_id || 'local';
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    return `GET:${tenantId}:${url}`;
  }

  // -------------------------------------------------------------------------
  // HTTP Methods
  // -------------------------------------------------------------------------

  /**
   * Make a GET request (deduplicated — concurrent identical GETs share one inflight request)
   */
  async get(endpoint: string, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const key = this.buildDedupKey(endpoint);

    // Dedup: if an identical GET is already inflight, return a clone of the same response
    const existing = this.inflightGets.get(key);
    if (existing) {
      return existing.then(r => r.clone());
    }

    const promise = this.fetchWithRetry(url, {
      ...options,
      method: 'GET',
      headers: this.buildHeaders(options?.headers),
    }).finally(() => {
      this.inflightGets.delete(key);
    });

    this.inflightGets.set(key, promise);
    return promise;
  }

  /**
   * Make a POST request
   */
  async post(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const isFormData = data instanceof FormData;

    const headers = isFormData
      ? this.buildHeadersWithoutContentType(options?.headers)
      : this.buildHeaders(options?.headers);

    const body = isFormData ? data : (data ? JSON.stringify(data) : undefined);

    return this.fetchWithRetry(url, {
      ...options,
      method: 'POST',
      headers,
      body,
    });
  }

  /**
   * Make a PUT request
   */
  async put(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    return this.fetchWithRetry(url, {
      ...options,
      method: 'PUT',
      headers: this.buildHeaders(options?.headers),
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a PATCH request
   */
  async patch(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    return this.fetchWithRetry(url, {
      ...options,
      method: 'PATCH',
      headers: this.buildHeaders(options?.headers),
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  /**
   * Make a DELETE request
   */
  async delete(endpoint: string, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    return this.fetchWithRetry(url, {
      ...options,
      method: 'DELETE',
      headers: this.buildHeaders(options?.headers),
    });
  }
}
