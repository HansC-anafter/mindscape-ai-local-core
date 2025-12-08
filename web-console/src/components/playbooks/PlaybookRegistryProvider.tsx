'use client';

/**
 * PlaybookRegistryProvider - Provider component to initialize PlaybookRegistry
 *
 * This component should be placed high in the component tree (e.g., in root layout)
 * to ensure playbooks are loaded early in the application lifecycle.
 */

import React, { useEffect, useState } from 'react';
import { getPlaybookRegistry, loadInstalledPlaybooks } from '@/playbook';
import { createLocalExecutionContext } from '@/types/execution-context';

interface PlaybookRegistryProviderProps {
  children: React.ReactNode;
}

/**
 * PlaybookRegistryProvider
 *
 * Initializes PlaybookRegistry and loads installed playbooks.
 * Uses local execution context by default (can be overridden by ExecutionContextProvider).
 */
export function PlaybookRegistryProvider({
  children
}: PlaybookRegistryProviderProps) {
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function initializeRegistry() {
      try {
        const registry = getPlaybookRegistry();
        const defaultContext = createLocalExecutionContext('default-workspace');

        await loadInstalledPlaybooks(registry, defaultContext);

        if (mounted) {
          setIsInitialized(true);
        }
      } catch (error) {
        console.error('Failed to initialize PlaybookRegistry:', error);
        if (mounted) {
          setIsInitialized(true);
        }
      }
    }

    initializeRegistry();

    return () => {
      mounted = false;
    };
  }, []);

  return <>{children}</>;
}

