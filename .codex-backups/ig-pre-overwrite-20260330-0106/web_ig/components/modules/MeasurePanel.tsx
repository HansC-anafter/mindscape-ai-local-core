'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { BarChart3 } from 'lucide-react';
import type { IGPost } from '../types';
import type { Metrics } from './measure/types';
import { useMeasureMetrics } from './measure/hooks/useMeasureMetrics';
import { useMeasureAnalysis } from './measure/hooks/useMeasureAnalysis';
import { MeasureHeader } from './measure/components/MeasureHeader';
import { MetricsCards } from './measure/components/MetricsCards';
import { MeasureAnalysisPanel } from './measure/components/MeasureAnalysisPanel';
import { AdvancedFeaturesPanel } from './measure/components/AdvancedFeaturesPanel';
import { BackfillDialog } from './measure/components/BackfillDialog';
import { executeWorkspacePlaybook } from './api';

interface MeasurePanelProps {
  workspaceId: string;
  apiUrl: string;
  selectedPostId: string | null;
  posts: IGPost[];
  onPostSelect: (postId: string) => void;
}

export default function MeasurePanel({
  workspaceId,
  apiUrl,
  selectedPostId,
  posts,
  onPostSelect
}: MeasurePanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [selectedPost, setSelectedPost] = useState<IGPost | null>(null);
  const [loading, setLoading] = useState(false);
  const [showBackfillDialog, setShowBackfillDialog] = useState(false);
  const [backfillMetrics, setBackfillMetrics] = useState<Partial<Metrics>>({});
  const { metrics } = useMeasureMetrics(selectedPost);
  const { analysis, loading: analysisLoading, reload: reloadAnalysis } = useMeasureAnalysis({ apiUrl, workspaceId, post: selectedPost });

  useEffect(() => {
    if (selectedPostId) {
      const post = posts.find(p => p.id === selectedPostId);
      setSelectedPost(post || null);
    } else {
      setSelectedPost(null);
    }
  }, [selectedPostId, posts]);

  const handleBackfill = async () => {
    if (!selectedPost || !selectedPost.post_path) {
      alert('Please select a post first');
      return;
    }

    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_metrics_backfill',
        inputs: {
          action: 'backfill',
          workspace_id: workspaceId,
          post_path: selectedPost.post_path || selectedPost.artifact_id,
          metrics: backfillMetrics,
          backfill_source: 'manual'
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        await reloadAnalysis();
        setShowBackfillDialog(false);
        setBackfillMetrics({});
        alert('Metrics backfilled successfully!');
      } else {
        const error = await response.json();
        alert(`Backfill failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to backfill metrics:', err);
      alert(`Backfill failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTrackElements = async () => {
    if (!selectedPost || !selectedPost.post_path) {
      alert('Please select a post first');
      return;
    }
    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_metrics_backfill',
        inputs: {
          action: 'track_elements',
          workspace_id: workspaceId,
          post_path: selectedPost.post_path,
        },
        execution_mode: 'sync',
      });
      if (response.ok) {
        await reloadAnalysis();
        alert('Performance element tracking completed');
      } else {
        alert('Tracking failed');
      }
    } catch (err) {
      console.error('Failed to track elements:', err);
      alert('Tracking failed');
    } finally {
      setLoading(false);
    }
  };

  const handleWriteRules = async () => {
    if (!selectedPost || !selectedPost.post_path) {
      alert('Please select a post first');
      return;
    }
    const rules = prompt('Enter performance rules (JSON format)');
    if (!rules) return;

    setLoading(true);
    try {
      const parsedRules = JSON.parse(rules);
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_metrics_backfill',
        inputs: {
          action: 'write_rules',
          workspace_id: workspaceId,
          post_path: selectedPost.post_path,
          rules: parsedRules,
        },
        execution_mode: 'sync',
      });
      if (response.ok) {
        alert('Performance rules written successfully');
      } else {
        alert('Write failed');
      }
    } catch (err) {
      console.error('Failed to write rules:', err);
      alert('Write failed');
    } finally {
      setLoading(false);
    }
  };

  const handleAggregateSeries = async () => {
    const seriesCode = prompt('Enter series code');
    if (!seriesCode) return;

    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_metrics_backfill',
        inputs: {
          action: 'aggregate_series',
          workspace_id: workspaceId,
          series_code: seriesCode,
        },
        execution_mode: 'sync',
      });
      if (response.ok) {
        const data = await response.json();
        alert(`Series aggregation completed: ${JSON.stringify(data.result?.aggregation || {})}`);
      } else {
        alert('Aggregation failed');
      }
    } catch (err) {
      console.error('Failed to aggregate series:', err);
      alert('Aggregation failed');
    } finally {
      setLoading(false);
    }
  };

  if (!selectedPost) {
    return (
      <div className="h-full flex items-center justify-center p-4">
        <div className="text-center text-gray-500 dark:text-gray-400">
          <BarChart3 className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p className="text-sm">Please select a post to view metrics data</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-4">
      <MeasureHeader
        postSummaryText={selectedPost.text?.substring(0, 50) || selectedPost.artifact_id}
        onOpenBackfill={() => setShowBackfillDialog(true)}
      />

      <div className="flex-1 overflow-y-auto space-y-4">
        <MetricsCards metrics={metrics} />

        {analysis && <MeasureAnalysisPanel analysis={analysis} />}

        {(loading || analysisLoading) && !analysis && (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            Loading analysis...
          </div>
        )}

        <AdvancedFeaturesPanel
          loading={loading}
          disabled={!selectedPost || !selectedPost.post_path}
          onTrackElements={handleTrackElements}
          onWriteRules={handleWriteRules}
          onAggregateSeries={handleAggregateSeries}
        />
      </div>

      <BackfillDialog
        open={showBackfillDialog}
        loading={loading}
        metrics={backfillMetrics}
        onMetricsChange={setBackfillMetrics}
        onConfirm={handleBackfill}
        onCancel={() => {
          setShowBackfillDialog(false);
          setBackfillMetrics({});
        }}
      />
    </div>
  );
}
