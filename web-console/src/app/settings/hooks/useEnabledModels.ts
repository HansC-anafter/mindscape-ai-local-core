'use client';

import { useState, useEffect, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';

export interface EnabledModel {
  id: number;
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  display_name: string;
  description: string;
  enabled: boolean;
  is_latest?: boolean;
  is_recommended?: boolean;
  is_deprecated?: boolean;
  dimensions?: number;
  context_window?: number;
  icon?: string;
}

export function useEnabledModels(modelType?: 'chat' | 'embedding') {
  const [enabledModels, setEnabledModels] = useState<EnabledModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadEnabledModels = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      params.set('enabled', 'true');
      if (modelType) {
        params.set('model_type', modelType);
      }

      const data = await settingsApi.get<EnabledModel[]>(
        `/api/v1/system-settings/models?${params.toString()}`
      );

      setEnabledModels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load enabled models');
      console.error('Failed to load enabled models:', err);
      setEnabledModels([]);
    } finally {
      setLoading(false);
    }
  }, [modelType]);

  useEffect(() => {
    loadEnabledModels();
  }, [loadEnabledModels]);

  return {
    enabledModels,
    loading,
    error,
    refresh: loadEnabledModels,
  };
}

