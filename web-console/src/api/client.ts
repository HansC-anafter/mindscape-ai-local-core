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
        'http://localhost:8000';
    } else {
      this.baseUrl =
        process.env.NEXT_PUBLIC_API_URL ||
        'http://localhost:8000';
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
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
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

    return fetch(url, {
      ...options,
      method: 'POST',
      headers: this.buildHeaders(options?.headers),
      body: data ? JSON.stringify(data) : undefined
    });
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

