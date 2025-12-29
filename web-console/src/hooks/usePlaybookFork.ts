'use client';

import { useState, useCallback } from 'react';
import { getApiBaseUrl } from '../lib/api-url';

const API_URL = getApiBaseUrl();

export interface ForkPlaybookRequest {
  target_workspace_id: string;
  new_playbook_code?: string;
  new_title?: string;
}

export interface ForkPlaybookResponse {
  playbook_code: string;
  title: string;
  scope: 'workspace';
  message: string;
}

interface UsePlaybookForkReturn {
  forking: boolean;
  error: string | null;
  forkPlaybook: (playbookCode: string, request: ForkPlaybookRequest) => Promise<ForkPlaybookResponse>;
}

export function usePlaybookFork(): UsePlaybookForkReturn {
  const [forking, setForking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forkPlaybook = useCallback(async (
    playbookCode: string,
    request: ForkPlaybookRequest
  ): Promise<ForkPlaybookResponse> => {
    setForking(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/playbooks/${playbookCode}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || `Failed to fork playbook: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fork playbook';
      setError(errorMessage);
      throw err;
    } finally {
      setForking(false);
    }
  }, []);

  return {
    forking,
    error,
    forkPlaybook,
  };
}

