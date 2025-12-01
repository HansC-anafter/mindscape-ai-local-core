'use client';

import { useState, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';
import type { CapabilityPack } from '../types';

interface UsePacksReturn {
  loading: boolean;
  packs: CapabilityPack[];
  installingPack: string | null;
  error: string | null;
  loadPacks: () => Promise<void>;
  installPack: (packId: string) => Promise<void>;
  clearError: () => void;
}

export function usePacks(): UsePacksReturn {
  const [loading, setLoading] = useState(false);
  const [packs, setPacks] = useState<CapabilityPack[]>([]);
  const [installingPack, setInstallingPack] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPacks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await settingsApi.get<CapabilityPack[]>('/api/v1/capability-packs/');
      setPacks(
        data.map((pack) => ({
          id: pack.id,
          name: pack.name,
          description: pack.description,
          icon: pack.icon,
          ai_members: pack.ai_members || [],
          capabilities: pack.capabilities || [],
          playbooks: pack.playbooks || [],
          required_tools: pack.required_tools || [],
          installed: pack.installed || false,
        }))
      );
    } catch (err) {
      console.error('Failed to load packs:', err);
      setPacks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const installPack = useCallback(async (packId: string) => {
    setInstallingPack(packId);
    try {
      await settingsApi.post(`/api/v1/capability-packs/${packId}/install`);
      await loadPacks();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to install pack';
      setError(errorMessage);
      throw err;
    } finally {
      setInstallingPack(null);
    }
  }, [loadPacks]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    loading,
    packs,
    installingPack,
    error,
    loadPacks,
    installPack,
    clearError,
  };
}
