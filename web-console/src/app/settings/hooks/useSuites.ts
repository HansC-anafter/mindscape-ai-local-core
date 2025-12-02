'use client';

import { useState, useCallback } from 'react';
import { settingsApi } from '../utils/settingsApi';

export interface CapabilitySuite {
  id: string;
  name: string;
  description: string;
  icon?: string;
  packs: string[];
  ai_members: string[];
  capabilities: string[];
  playbooks: string[];
  required_tools: string[];
  installed: boolean;
}

interface UseSuitesReturn {
  loading: boolean;
  suites: CapabilitySuite[];
  installingSuite: string | null;
  error: string | null;
  loadSuites: () => Promise<void>;
  installSuite: (suiteId: string) => Promise<void>;
  clearError: () => void;
}

export function useSuites(): UseSuitesReturn {
  const [loading, setLoading] = useState(false);
  const [suites, setSuites] = useState<CapabilitySuite[]>([]);
  const [installingSuite, setInstallingSuite] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSuites = useCallback(async () => {
    setLoading(true);
    try {
      const data = await settingsApi.get<CapabilitySuite[]>('/api/v1/capability-suites/');
      setSuites(data);
    } catch (err) {
      console.error('Failed to load suites:', err);
      setSuites([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const installSuite = useCallback(async (suiteId: string) => {
    setInstallingSuite(suiteId);
    try {
      await settingsApi.post(`/api/v1/capability-suites/${suiteId}/install`);
      await loadSuites();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to install suite';
      setError(errorMessage);
      throw err;
    } finally {
      setInstallingSuite(null);
    }
  }, [loadSuites]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    loading,
    suites,
    installingSuite,
    error,
    loadSuites,
    installSuite,
    clearError,
  };
}

