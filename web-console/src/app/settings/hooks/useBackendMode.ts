'use client';

import { useState, useEffect, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';

export type BackendMode = 'local' | 'remote_crs';

interface UseBackendModeReturn {
  mode: BackendMode;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const PROFILE_ID = 'default-user';

export function useBackendMode(): UseBackendModeReturn {
  const [mode, setMode] = useState<BackendMode>('local');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await settingsApi.get<{ current_mode: BackendMode }>(
        `/api/v1/config/backend?profile_id=${PROFILE_ID}`
      );
      setMode(data.current_mode);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load backend mode';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    mode,
    loading,
    error,
    refresh,
  };
}
