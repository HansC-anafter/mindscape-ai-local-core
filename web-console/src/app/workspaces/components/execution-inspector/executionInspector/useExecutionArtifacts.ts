import { useEffect, useState } from 'react';

import type { Artifact } from '../types/execution';
import { filterArtifactsForExecution } from './executionInspectorState';

export interface UseExecutionArtifactsResult {
  artifacts: Artifact[];
  originalArtifacts: Artifact[];
  artifactsLoading: boolean;
}

export function useExecutionArtifacts(
  executionId: string,
  workspaceId: string,
  apiUrl: string,
): UseExecutionArtifactsResult {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [originalArtifacts, setOriginalArtifacts] = useState<Artifact[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);

  useEffect(() => {
    if (!executionId || !workspaceId) {
      setArtifacts([]);
      setOriginalArtifacts([]);
      return;
    }

    let cancelled = false;
    setArtifactsLoading(true);

    const fetchArtifacts = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?limit=100&include_content=false&include_preview=false`
        );
        if (cancelled) return;

        if (response.ok) {
          const data = await response.json();
          const convertedArtifacts = filterArtifactsForExecution(
            data.artifacts || [],
            apiUrl,
            workspaceId,
            executionId,
          );
          if (!cancelled) {
            setOriginalArtifacts(convertedArtifacts);
            setArtifacts(convertedArtifacts);
          }
        } else {
          console.error('[ExecutionInspector] Failed to fetch artifacts:', response.status, response.statusText);
        }
      } catch (error) {
        console.error('[ExecutionInspector] Failed to fetch artifacts:', error);
        if (!cancelled) {
          setArtifacts([]);
          setOriginalArtifacts([]);
        }
      } finally {
        if (!cancelled) {
          setArtifactsLoading(false);
        }
      }
    };

    fetchArtifacts();

    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  return {
    artifacts,
    originalArtifacts,
    artifactsLoading,
  };
}
