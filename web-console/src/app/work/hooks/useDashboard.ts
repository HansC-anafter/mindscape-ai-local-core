'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet } from '../utils/apiClient';
import type {
  DashboardSummaryDTO,
  InboxItemDTO,
  CaseCardDTO,
  AssignmentCardDTO,
  DashboardQuery,
  PaginatedResponse,
} from '../types';

/**
 * Request deduplication and retry limit management
 */
class RequestManager {
  private pendingRequests: Map<string, Promise<any>> = new Map();
  private retryCounts: Map<string, number> = new Map();
  private readonly maxRetries = 2;
  private readonly retryDelayMs = 2000;

  async execute<T>(
    key: string,
    requestFn: () => Promise<T>
  ): Promise<T> {
    // Deduplicate: if same request is already pending, return existing promise
    const existingRequest = this.pendingRequests.get(key);
    if (existingRequest) {
      return existingRequest;
    }

    // Create new request
    const requestPromise = this.executeWithRetry(key, requestFn);
    this.pendingRequests.set(key, requestPromise);

    try {
      const result = await requestPromise;
      return result;
    } finally {
      this.pendingRequests.delete(key);
    }
  }

  private async executeWithRetry<T>(
    key: string,
    requestFn: () => Promise<T>
  ): Promise<T> {
    const retryCount = this.retryCounts.get(key) || 0;

    try {
      const result = await requestFn();
      // Reset retry count on success
      this.retryCounts.delete(key);
      return result;
    } catch (error) {
      const isNetworkError = (error as any)?.isNetworkError === true;

      // Only retry network errors, not HTTP errors (4xx, 5xx)
      if (isNetworkError && retryCount < this.maxRetries) {
        this.retryCounts.set(key, retryCount + 1);
        await new Promise((resolve) => setTimeout(resolve, this.retryDelayMs));
        return this.executeWithRetry(key, requestFn);
      }

      // Max retries reached or non-retryable error
      this.retryCounts.delete(key);
      throw error;
    }
  }

  clear(): void {
    this.pendingRequests.clear();
    this.retryCounts.clear();
  }
}

const requestManager = new RequestManager();

interface UseDashboardSummaryOptions {
  scope?: string;
  view?: string;
  enabled?: boolean;
}

export function useDashboardSummary(options: UseDashboardSummaryOptions = {}) {
  const { scope = 'global', view = 'my_work', enabled = true } = options;
  const [data, setData] = useState<DashboardSummaryDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!enabled) return;

    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setLoading(true);
    setError(null);

    const requestKey = `summary:${scope}:${view}`;

    try {
      const summary = await requestManager.execute(requestKey, async () => {
        return apiGet<DashboardSummaryDTO>(
          `/api/v1/dashboard/summary?scope=${scope}&view=${view}`,
          { signal: abortControllerRef.current?.signal }
        );
      });
      setData(summary);
    } catch (err) {
      // Ignore aborted requests
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      // Handle authentication and authorization errors
      if (status === 401) {
        error.message = 'Authentication required. Please log in to access the dashboard.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to access this resource.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
    } finally {
      setLoading(false);
    }
  }, [scope, view, enabled]);

  useEffect(() => {
    fetchSummary();

    return () => {
      // Cleanup: abort request on unmount or dependency change
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchSummary]);

  return { data, loading, error, refetch: fetchSummary };
}

export function useDashboardInbox(query: DashboardQuery = {}) {
  const [data, setData] = useState<PaginatedResponse<InboxItemDTO> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchInbox = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      scope: query.scope || 'global',
      sort_by: query.sort_by || 'auto',
      sort_order: query.sort_order || 'desc',
      limit: String(query.limit || 50),
      offset: String(query.offset || 0),
    });

    const requestKey = `inbox:${params.toString()}`;

    try {
      const inbox = await requestManager.execute(requestKey, async () => {
        return apiGet<PaginatedResponse<InboxItemDTO>>(
          `/api/v1/dashboard/inbox?${params}`,
          { signal: abortControllerRef.current?.signal }
        );
      });
      setData(inbox);
    } catch (err) {
      // Ignore aborted requests
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to access the inbox.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to access this resource.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    fetchInbox();

    return () => {
      // Cleanup: abort request on unmount or dependency change
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchInbox]);

  return { data, loading, error, refetch: fetchInbox };
}

export function useDashboardCases(query: DashboardQuery = {}) {
  const [data, setData] = useState<PaginatedResponse<CaseCardDTO> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchCases = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      scope: query.scope || 'global',
      sort_by: query.sort_by || 'auto',
      sort_order: query.sort_order || 'desc',
      limit: String(query.limit || 50),
      offset: String(query.offset || 0),
    });

    const requestKey = `cases:${params.toString()}`;

    try {
      const cases = await requestManager.execute(requestKey, async () => {
        return apiGet<PaginatedResponse<CaseCardDTO>>(
          `/api/v1/dashboard/cases?${params}`,
          { signal: abortControllerRef.current?.signal }
        );
      });
      setData(cases);
    } catch (err) {
      // Ignore aborted requests
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to access cases.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to access this resource.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    fetchCases();

    return () => {
      // Cleanup: abort request on unmount or dependency change
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchCases]);

  return { data, loading, error, refetch: fetchCases };
}

export function useDashboardAssignments(query: DashboardQuery = {}) {
  const [data, setData] = useState<PaginatedResponse<AssignmentCardDTO> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchAssignments = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      scope: query.scope || 'global',
      view: query.view || 'assigned_to_me',
      sort_by: query.sort_by || 'auto',
      sort_order: query.sort_order || 'desc',
      limit: String(query.limit || 50),
      offset: String(query.offset || 0),
    });

    const requestKey = `assignments:${params.toString()}`;

    try {
      const assignments = await requestManager.execute(requestKey, async () => {
        return apiGet<PaginatedResponse<AssignmentCardDTO>>(
          `/api/v1/dashboard/assignments?${params}`,
          { signal: abortControllerRef.current?.signal }
        );
      });
      setData(assignments);
    } catch (err) {
      // Ignore aborted requests
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to access assignments.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to access this resource.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    fetchAssignments();

    return () => {
      // Cleanup: abort request on unmount or dependency change
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchAssignments]);

  return { data, loading, error, refetch: fetchAssignments };
}

