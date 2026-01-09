'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiDelete } from '../utils/apiClient';
import type { SavedViewDTO, SavedViewCreate } from '../types';

export function useSavedViews() {
  const [views, setViews] = useState<SavedViewDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchViews = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await apiGet<SavedViewDTO[]>('/api/v1/dashboard/saved-views');
      setViews(data);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to access saved views.';
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
  }, []);

  const createView = useCallback(async (viewData: SavedViewCreate): Promise<SavedViewDTO | null> => {
    setLoading(true);
    setError(null);

    try {
      const newView = await apiPost<SavedViewDTO>('/api/v1/dashboard/saved-views', viewData);
      await fetchViews();
      return newView;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to create saved views.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to create saved views.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fetchViews]);

  const deleteView = useCallback(async (viewId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await apiDelete(`/api/v1/dashboard/saved-views/${viewId}`);
      await fetchViews();
      return true;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      const status = (err as any)?.status;

      if (status === 401) {
        error.message = 'Authentication required. Please log in to delete saved views.';
        (error as any).status = 401;
        (error as any).isAuthError = true;
      } else if (status === 403) {
        error.message = 'Access denied. You do not have permission to delete saved views.';
        (error as any).status = 403;
        (error as any).isAuthError = true;
      }

      setError(error);
      return false;
    } finally {
      setLoading(false);
    }
  }, [fetchViews]);

  useEffect(() => {
    fetchViews();
  }, [fetchViews]);

  return {
    views,
    loading,
    error,
    refetch: fetchViews,
    createView,
    deleteView,
  };
}

