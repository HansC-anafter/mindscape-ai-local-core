import { useState, useEffect } from 'react';
import type { PlaybookMetadata, PlaybookStepDefinition } from '../types/execution';
import { parsePlaybookSteps } from '../utils/parsePlaybookSteps';

export interface UsePlaybookMetadataResult {
  playbookMetadata: PlaybookMetadata | null;
  playbookStepDefinitions: PlaybookStepDefinition[];
  loading: boolean;
  error: Error | null;
}

export function usePlaybookMetadata(
  execution: { playbook_code?: string; playbook_version?: string } | null,
  executionId: string | null,
  apiUrl: string
): UsePlaybookMetadataResult {
  const [playbookMetadata, setPlaybookMetadata] = useState<PlaybookMetadata | null>(null);
  const [playbookStepDefinitions, setPlaybookStepDefinitions] = useState<PlaybookStepDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // Reset state immediately when execution or executionId changes
    if (!execution?.playbook_code || !executionId) {
      setPlaybookMetadata(null);
      setPlaybookStepDefinitions([]);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    const currentPlaybookCode = execution.playbook_code;
    const currentExecutionId = executionId;

    const loadPlaybookMetadata = async () => {
      try {
        setError(null);
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/playbooks/${currentPlaybookCode}`
        );

        // Check if component was unmounted or execution/executionId changed
        if (cancelled || execution?.playbook_code !== currentPlaybookCode || executionId !== currentExecutionId) {
          return;
        }

        if (response.ok) {
          const data = await response.json();

          // Check again after async operation
          if (cancelled || execution?.playbook_code !== currentPlaybookCode || executionId !== currentExecutionId) {
            return;
          }

          setPlaybookMetadata(data);

          try {
            const stepDefs = parsePlaybookSteps(data);
            if (!cancelled && execution?.playbook_code === currentPlaybookCode && executionId === currentExecutionId) {
              if (stepDefs.length > 0) {
                setPlaybookStepDefinitions(stepDefs);
              } else {
                setPlaybookStepDefinitions([]);
              }
            }
          } catch (e) {
            console.warn('[usePlaybookMetadata] Failed to extract step definitions from playbook:', e);
            if (!cancelled && execution?.playbook_code === currentPlaybookCode && executionId === currentExecutionId) {
              setPlaybookStepDefinitions([]);
            }
          }
        } else if (response.status === 404) {
          // Check again after async operation
          if (cancelled || execution?.playbook_code !== currentPlaybookCode || executionId !== currentExecutionId) {
            return;
          }
          setPlaybookMetadata({
            playbook_code: execution.playbook_code || '',
            version: execution.playbook_version || '1.0.0'
          });
          setPlaybookStepDefinitions([]);
        } else {
          // Check again after async operation
          if (cancelled || execution?.playbook_code !== currentPlaybookCode || executionId !== currentExecutionId) {
            return;
          }
          const error = new Error(`Failed to load playbook: ${response.status}`);
          setError(error);
          setPlaybookMetadata({
            playbook_code: execution.playbook_code || '',
            version: execution.playbook_version || '1.0.0'
          });
          setPlaybookStepDefinitions([]);
        }
      } catch (err) {
        // Check again after async operation
        if (cancelled || execution?.playbook_code !== currentPlaybookCode || executionId !== currentExecutionId) {
          return;
        }
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        setPlaybookMetadata({
          playbook_code: execution.playbook_code || '',
          version: execution.playbook_version || '1.0.0'
        });
        setPlaybookStepDefinitions([]);
      } finally {
        if (!cancelled && execution?.playbook_code === currentPlaybookCode && executionId === currentExecutionId) {
          setLoading(false);
        }
      }
    };

    loadPlaybookMetadata();

    // Cleanup function
    return () => {
      cancelled = true;
    };
  }, [execution?.playbook_code, execution?.playbook_version, apiUrl, executionId]);

  return {
    playbookMetadata,
    playbookStepDefinitions,
    loading,
    error,
  };
}
