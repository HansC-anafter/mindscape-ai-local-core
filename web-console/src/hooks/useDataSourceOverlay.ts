'use client';

import { useState, useCallback } from 'react';
import { useResourceBindings } from './useResourceBindings';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface DataSourceOverlay {
  access_mode_override?: 'read' | 'write' | 'admin';
  display_name?: string;
  enabled?: boolean;
}

export interface DataSourceWithOverlay {
  data_source_id: string;
  data_source_name: string;
  data_source_type: string;
  original_access_mode: 'read' | 'write' | 'admin';
  effective_access_mode: 'read' | 'write' | 'admin';
  display_name?: string;
  enabled: boolean;
  overlay_applied: boolean;
}

interface UseDataSourceOverlayReturn {
  dataSources: DataSourceWithOverlay[];
  loading: boolean;
  error: string | null;
  loadDataSources: () => Promise<void>;
  getDataSourceOverlay: (dataSourceId: string) => DataSourceOverlay | null;
  updateDataSourceOverlay: (dataSourceId: string, overlay: Partial<DataSourceOverlay>) => Promise<void>;
  validateAccessMode: (original: string, override: string) => boolean;
}

const ACCESS_MODE_ORDER: Record<string, number> = {
  read: 1,
  write: 2,
  admin: 3,
};

export function useDataSourceOverlay(workspaceId: string): UseDataSourceOverlayReturn {
  const { bindings, getBinding, updateBinding, createBinding } = useResourceBindings(workspaceId);
  const [dataSources, setDataSources] = useState<DataSourceWithOverlay[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateAccessMode = useCallback((original: string, override: string): boolean => {
    const originalLevel = ACCESS_MODE_ORDER[original.toLowerCase()] || 0;
    const overrideLevel = ACCESS_MODE_ORDER[override.toLowerCase()] || 0;
    return overrideLevel <= originalLevel;
  }, []);

  const getDataSourceOverlay = useCallback((dataSourceId: string): DataSourceOverlay | null => {
    const binding = getBinding('data_source', dataSourceId);
    if (!binding) return null;

    return {
      access_mode_override: binding.overrides?.access_mode_override,
      display_name: binding.overrides?.display_name,
      enabled: binding.overrides?.enabled,
    };
  }, [getBinding]);

  const loadDataSources = useCallback(async () => {
    if (!workspaceId) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/data-sources/?workspace_id=${workspaceId}`);
      if (!response.ok) {
        throw new Error(`Failed to load data sources: ${response.statusText}`);
      }
      const data = await response.json();
      const sourcesList = Array.isArray(data) ? data : [];

      const sourcesWithOverlay: DataSourceWithOverlay[] = sourcesList.map((source: any) => {
        const binding = getBinding('data_source', source.id || source.data_source_id);
        const originalAccessMode = source.access_mode || 'read';
        const effectiveAccessMode = binding?.overrides?.access_mode_override || binding?.access_mode || originalAccessMode;
        const displayName = binding?.overrides?.display_name || source.name || source.data_source_name;
        const isEnabled = binding?.overrides?.enabled !== undefined ? binding.overrides.enabled : source.enabled !== false;
        const overlayApplied = !!binding;

        return {
          data_source_id: source.id || source.data_source_id,
          data_source_name: source.name || source.data_source_name,
          data_source_type: source.data_source_type || source.type,
          original_access_mode: originalAccessMode,
          effective_access_mode: effectiveAccessMode,
          display_name: displayName,
          enabled: isEnabled,
          overlay_applied: overlayApplied,
        };
      });

      setDataSources(sourcesWithOverlay);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load data sources';
      setError(errorMessage);
      console.error('Failed to load data sources:', err);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, getBinding]);

  const updateDataSourceOverlay = useCallback(async (
    dataSourceId: string,
    overlay: Partial<DataSourceOverlay>
  ): Promise<void> => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setError(null);
    try {
      const binding = getBinding('data_source', dataSourceId);
      const currentOverrides = binding?.overrides || {};
      const updatedOverrides = {
        ...currentOverrides,
        ...overlay,
      };

      if (binding) {
        await updateBinding('data_source', dataSourceId, {
          access_mode: overlay.access_mode_override || binding.access_mode,
          overrides: updatedOverrides,
        });
      } else {
        await createBinding({
          resource_type: 'data_source',
          resource_id: dataSourceId,
          access_mode: overlay.access_mode_override || 'read',
          overrides: updatedOverrides,
        });
      }

      await loadDataSources();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to update data source overlay';
      setError(errorMessage);
      throw err;
    }
  }, [workspaceId, getBinding, updateBinding, createBinding, loadDataSources]);

  return {
    dataSources,
    loading,
    error,
    loadDataSources,
    getDataSourceOverlay,
    updateDataSourceOverlay,
    validateAccessMode,
  };
}

