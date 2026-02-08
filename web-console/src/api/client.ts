/**
 * MindscapeAPIClient - Unified API client for Local and Cloud environments
 *
 * This client automatically handles differences between Local and Cloud:
 * - API endpoint URLs
 * - Authentication headers (JWT tokens, tenant/group IDs)
 * - Request/response handling
 *
 * Playbook components should use this client instead of directly calling fetch.
 */

import { ExecutionContext } from '@/types/execution-context';

export class MindscapeAPIClient {
  private baseUrl: string;
  private context: ExecutionContext;

  constructor(context: ExecutionContext) {
    this.context = context;

    if (context.tags?.mode === 'cloud') {
      this.baseUrl =
        process.env.NEXT_PUBLIC_CLOUD_API_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        'http://localhost:8500';  // 新默认 Cloud API 端口
    } else {
      this.baseUrl =
        process.env.NEXT_PUBLIC_API_URL ||
        'http://localhost:8200';  // 新默认后端 API 端口
    }
  }

  /**
   * Get authentication token for Cloud mode
   * Returns null if no token is available or in Local mode
   */
  private getAuthToken(): string | null {
    if (this.context.tags?.mode === 'cloud') {
      return null;
    }
    return null;
  }

  /**
   * Build headers for API requests
   */
  private buildHeaders(customHeaders?: HeadersInit): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...customHeaders
    };

    if (this.context.tags?.mode === 'cloud') {
      const token = this.getAuthToken();
      const headersRecord = headers as Record<string, string>;

      if (token) {
        headersRecord['Authorization'] = `Bearer ${token}`;
      }

      if (this.context.tags.tenant_id) {
        headersRecord['X-Tenant-ID'] = this.context.tags.tenant_id;
      }

      if (this.context.tags.group_id) {
        headersRecord['X-Group-ID'] = this.context.tags.group_id;
      }
    }

    return headers;
  }

  /**
   * Make a GET request
   */
  async get(endpoint: string, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http')
      ? endpoint
      : `${this.baseUrl}${endpoint}`;

    return fetch(url, {
      ...options,
      method: 'GET',
      headers: this.buildHeaders(options?.headers)
    });
  }

  /**
   * Make a POST request
   */
  async post(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http')
      ? endpoint
      : `${this.baseUrl}${endpoint}`;

    // Check if data is FormData
    const isFormData = data instanceof FormData;

    // Build headers - exclude Content-Type for FormData (browser will set it with boundary)
    const headers = isFormData
      ? this.buildHeadersWithoutContentType(options?.headers)
      : this.buildHeaders(options?.headers);

    // Use FormData directly or stringify JSON
    const body = isFormData ? data : (data ? JSON.stringify(data) : undefined);

    return fetch(url, {
      ...options,
      method: 'POST',
      headers,
      body
    });
  }

  /**
   * Build headers without Content-Type (for FormData)
   * Preserves all custom headers except Content-Type
   */
  private buildHeadersWithoutContentType(customHeaders?: HeadersInit): HeadersInit {
    // Start with custom headers, excluding Content-Type
    const headers: Record<string, string> = {};

    if (customHeaders) {
      if (customHeaders instanceof Headers) {
        customHeaders.forEach((value, key) => {
          if (key.toLowerCase() !== 'content-type') {
            headers[key] = value;
          }
        });
      } else if (Array.isArray(customHeaders)) {
        customHeaders.forEach(([key, value]) => {
          if (key.toLowerCase() !== 'content-type') {
            headers[key] = value;
          }
        });
      } else {
        Object.entries(customHeaders).forEach(([key, value]) => {
          if (key.toLowerCase() !== 'content-type') {
            headers[key] = value as string;
          }
        });
      }
    }

    // Add context-specific headers
    if (this.context.tags?.mode === 'cloud') {
      const token = this.getAuthToken();

      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      if (this.context.tags.tenant_id) {
        headers['X-Tenant-ID'] = this.context.tags.tenant_id;
      }

      if (this.context.tags.group_id) {
        headers['X-Group-ID'] = this.context.tags.group_id;
      }
    }

    return headers;
  }

  /**
   * Make a PUT request
   */
  async put(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http')
      ? endpoint
      : `${this.baseUrl}${endpoint}`;

    return fetch(url, {
      ...options,
      method: 'PUT',
      headers: this.buildHeaders(options?.headers),
      body: data ? JSON.stringify(data) : undefined
    });
  }

  /**
   * Make a PATCH request
   */
  async patch(endpoint: string, data?: any, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http')
      ? endpoint
      : `${this.baseUrl}${endpoint}`;

    return fetch(url, {
      ...options,
      method: 'PATCH',
      headers: this.buildHeaders(options?.headers),
      body: data ? JSON.stringify(data) : undefined
    });
  }

  /**
   * Make a DELETE request
   */
  async delete(endpoint: string, options?: RequestInit): Promise<Response> {
    const url = endpoint.startsWith('http')
      ? endpoint
      : `${this.baseUrl}${endpoint}`;

    return fetch(url, {
      ...options,
      method: 'DELETE',
      headers: this.buildHeaders(options?.headers)
    });
  }
}

