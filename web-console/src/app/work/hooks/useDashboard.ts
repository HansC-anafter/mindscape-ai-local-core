'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
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
  const fetchedKeyRef = useRef<string>('');
  const mountedRef = useRef(true);

  const queryKey = JSON.stringify(query);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    // Only fetch if query actually changed
    if (fetchedKeyRef.current === queryKey) return;
    fetchedKeyRef.current = queryKey;

    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const q = query;
    const params = new URLSearchParams({
      scope: q.scope || 'global',
      sort_by: q.sort_by || 'auto',
      sort_order: q.sort_order || 'desc',
      limit: String(q.limit || 50),
      offset: String(q.offset || 0),
    });

    setLoading(true);
    setError(null);

    apiGet<PaginatedResponse<InboxItemDTO>>(
      `/api/v1/dashboard/inbox?${params}`,
      { signal: abortController.signal }
    ).then((inbox) => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setData(inbox);
      }
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      if (!mountedRef.current) return;
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
    }).finally(() => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setLoading(false);
      }
    });

    return () => {
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  const refetch = useCallback(() => {
    fetchedKeyRef.current = ''; // Reset guard to allow re-fetch
    // Trigger re-render to re-run the effect
    setLoading((prev) => prev);
  }, []);

  return { data, loading, error, refetch };
}

export function useDashboardCases(query: DashboardQuery = {}) {
  const [data, setData] = useState<PaginatedResponse<CaseCardDTO> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fetchedKeyRef = useRef<string>('');
  const mountedRef = useRef(true);

  const queryKey = JSON.stringify(query);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (fetchedKeyRef.current === queryKey) return;
    fetchedKeyRef.current = queryKey;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const q = query;
    const params = new URLSearchParams({
      scope: q.scope || 'global',
      sort_by: q.sort_by || 'auto',
      sort_order: q.sort_order || 'desc',
      limit: String(q.limit || 50),
      offset: String(q.offset || 0),
    });

    setLoading(true);
    setError(null);

    apiGet<PaginatedResponse<CaseCardDTO>>(
      `/api/v1/dashboard/cases?${params}`,
      { signal: abortController.signal }
    ).then((cases) => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setData(cases);
      }
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      if (!mountedRef.current) return;
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
    }).finally(() => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setLoading(false);
      }
    });

    return () => {
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  const refetch = useCallback(() => {
    fetchedKeyRef.current = '';
    setLoading((prev) => prev);
  }, []);

  return { data, loading, error, refetch };
}

export function useDashboardAssignments(query: DashboardQuery = {}) {
  const [data, setData] = useState<PaginatedResponse<AssignmentCardDTO> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fetchedKeyRef = useRef<string>('');
  const mountedRef = useRef(true);

  const queryKey = JSON.stringify(query);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (fetchedKeyRef.current === queryKey) return;
    fetchedKeyRef.current = queryKey;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const q = query;
    const params = new URLSearchParams({
      scope: q.scope || 'global',
      view: q.view || 'assigned_to_me',
      sort_by: q.sort_by || 'auto',
      sort_order: q.sort_order || 'desc',
      limit: String(q.limit || 50),
      offset: String(q.offset || 0),
    });

    setLoading(true);
    setError(null);

    apiGet<PaginatedResponse<AssignmentCardDTO>>(
      `/api/v1/dashboard/assignments?${params}`,
      { signal: abortController.signal }
    ).then((assignments) => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setData(assignments);
      }
    }).catch((err) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      if (!mountedRef.current) return;
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
    }).finally(() => {
      if (mountedRef.current && !abortController.signal.aborted) {
        setLoading(false);
      }
    });

    return () => {
      abortController.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey]);

  const refetch = useCallback(() => {
    fetchedKeyRef.current = '';
    setLoading((prev) => prev);
  }, []);

  return { data, loading, error, refetch };
}

