'use client';

import { useState, useEffect, useCallback } from 'react';

export interface ThreadBundle {
  thread_id: string;
  overview: {
    title: string;
    brief?: string;
    status: 'in_progress' | 'delivered' | 'pending_data';
    summary?: string;
    project_id?: string;
    labels: string[];
    pinned_scope?: any;
  };
  deliverables: ThreadDeliverable[];
  references: ThreadReference[];
  runs: ThreadRun[];
  sources: ThreadSource[];
}

export interface ThreadDeliverable {
  id: string;
  title: string;
  artifact_type: string;
  source: 'playbook' | 'connector' | 'manual' | 'ai_generated';
  source_event_id: string;
  status: 'draft' | 'final' | 'archived';
  updated_at: string;
}

export interface ThreadReference {
  id: string;
  source_type: 'obsidian' | 'notion' | 'wordpress' | 'local_file' | 'url' | 'google_drive';
  uri: string;
  title: string;
  snippet?: string;
  reason?: string;
  created_at: string;
  pinned_by: 'user' | 'ai';
}

export interface ThreadRun {
  id: string;
  playbook_name: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string;
  duration_ms?: number;
  steps_completed: number;
  steps_total: number;
  deliverable_ids: string[];
  result_summary?: string;
  storage_ref?: string;
}

export interface ThreadSource {
  id: string;
  type: 'wordpress_site' | 'obsidian_vault' | 'notion_db' | 'google_drive' | 'local_folder';
  identifier: string;
  display_name: string;
  permissions: ('read' | 'write')[];
  last_sync_at?: string;
  sync_status: 'connected' | 'disconnected' | 'syncing';
}

export function useThreadBundle(
  workspaceId: string,
  threadId: string | null,
  apiUrl: string = ''
) {
  const [bundle, setBundle] = useState<ThreadBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBundle = useCallback(async () => {
    if (!threadId) {
      setBundle(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/threads/${threadId}/bundle`
      );

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        throw new Error(`Failed to load bundle: ${response.status} - ${errorText.substring(0, 100)}`);
      }

      const data = await response.json();
      setBundle(data);
    } catch (err: any) {
      console.error('Failed to load thread bundle:', err);
      setError(err.message || 'Failed to load thread bundle');
      setBundle(null);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, threadId, apiUrl]);

  // Load bundle when threadId changes
  useEffect(() => {
    if (threadId) {
      loadBundle();
    } else {
      setBundle(null);
    }
  }, [threadId, loadBundle]);

  return {
    bundle,
    loading,
    error,
    reload: loadBundle,
  };
}
