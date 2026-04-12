import { useCallback, useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { IGPost } from '../../../types';
import type { Analysis } from '../types';
import { executeWorkspacePlaybook } from '../../api';

export function useMeasureAnalysis(params: {
  apiUrl: string;
  workspaceId: string;
  post: IGPost | null;
}) {
  const { apiUrl, workspaceId, post } = params;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAnalysis = useCallback(async (p: IGPost) => {
    if (!p.post_path) return;

    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_metrics_backfill',
        inputs: {
          action: 'analyze',
          workspace_id: workspaceId,
          post_path: p.post_path || p.artifact_id,
        },
        execution_mode: 'sync',
      });

      if (response.ok) {
        const data = await response.json();
        setAnalysis(data.result?.analysis || null);
      }
    } catch (err) {
      console.error('Failed to load analysis:', err);
    } finally {
      setLoading(false);
    }
  }, [client, workspaceId]);

  useEffect(() => {
    if (!post) {
      setAnalysis(null);
      return;
    }
    loadAnalysis(post);
  }, [post, loadAnalysis]);

  return { analysis, loading, reload: () => (post ? loadAnalysis(post) : Promise.resolve()) };
}

