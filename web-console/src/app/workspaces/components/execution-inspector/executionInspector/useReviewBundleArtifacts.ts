import { useCallback, useEffect, useState } from 'react';

import type { ReviewBundleArtifact } from '../types/execution';
import {
  applyReviewBundleArtifactUpdate,
  filterReviewBundlesForRun,
} from './executionInspectorState';

export interface UseReviewBundleArtifactsResult {
  reviewBundleArtifacts: ReviewBundleArtifact[];
  reviewBundlesLoading: boolean;
  handleReviewBundleArtifactUpdated: (updatedArtifact: ReviewBundleArtifact) => void;
}

export function useReviewBundleArtifacts(
  workspaceId: string,
  apiUrl: string,
  productionRunId: string | null,
): UseReviewBundleArtifactsResult {
  const [reviewBundleArtifacts, setReviewBundleArtifacts] = useState<ReviewBundleArtifact[]>([]);
  const [reviewBundlesLoading, setReviewBundlesLoading] = useState(false);

  useEffect(() => {
    if (!workspaceId || !productionRunId) {
      setReviewBundleArtifacts([]);
      setReviewBundlesLoading(false);
      return;
    }

    let cancelled = false;
    setReviewBundlesLoading(true);

    const fetchReviewBundles = async () => {
      try {
        const params = new URLSearchParams({
          kind: 'visual_acceptance_bundle',
          include_content: 'true',
          limit: '100',
        });
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?${params.toString()}`
        );
        if (cancelled) return;
        if (!response.ok) {
          throw new Error(`Failed to fetch review bundles: ${response.status}`);
        }
        const data = await response.json();
        const matchingBundles = filterReviewBundlesForRun(
          data.artifacts || [],
          apiUrl,
          workspaceId,
          productionRunId,
        );
        if (!cancelled) {
          setReviewBundleArtifacts(matchingBundles);
        }
      } catch (error) {
        console.error('[ExecutionInspector] Failed to fetch review bundles:', error);
        if (!cancelled) {
          setReviewBundleArtifacts([]);
        }
      } finally {
        if (!cancelled) {
          setReviewBundlesLoading(false);
        }
      }
    };

    void fetchReviewBundles();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, productionRunId, workspaceId]);

  const handleReviewBundleArtifactUpdated = useCallback((updatedArtifact: ReviewBundleArtifact) => {
    setReviewBundleArtifacts((current) => applyReviewBundleArtifactUpdate(current, updatedArtifact));
  }, []);

  return {
    reviewBundleArtifacts,
    reviewBundlesLoading,
    handleReviewBundleArtifactUpdated,
  };
}
