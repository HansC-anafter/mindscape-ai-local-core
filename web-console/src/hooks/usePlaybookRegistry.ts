/**
 * usePlaybookRegistry - Hook to initialize and access PlaybookRegistry
 *
 * Ensures PlaybookRegistry is initialized and playbooks are loaded.
 * This hook should be used in components that need to access playbook information.
 */

import { useEffect, useState } from 'react';
import { getPlaybookRegistry, loadInstalledPlaybooks } from '@/playbook';
import { useExecutionContext } from '@/contexts/ExecutionContextContext';

interface UsePlaybookRegistryResult {
  registry: ReturnType<typeof getPlaybookRegistry>;
  isLoading: boolean;
  error: Error | null;
}

/**
 * Hook to initialize and access PlaybookRegistry
 *
 * Automatically loads installed playbooks on mount.
 * Uses ExecutionContext to determine Local/Cloud mode.
 */
export function usePlaybookRegistry(): UsePlaybookRegistryResult {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const context = useExecutionContext();
  const registry = getPlaybookRegistry();

  useEffect(() => {
    let mounted = true;

    async function initializeRegistry() {
      try {
        setIsLoading(true);
        setError(null);

        await loadInstalledPlaybooks(registry, context);

        if (mounted) {
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setIsLoading(false);
        }
      }
    }

    initializeRegistry();

    return () => {
      mounted = false;
    };
  }, [context]);

  return {
    registry,
    isLoading,
    error
  };
}

