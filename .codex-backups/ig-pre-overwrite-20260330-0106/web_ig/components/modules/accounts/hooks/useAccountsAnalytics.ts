import { useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import { fetchWorkspaceArtifacts } from '../api';

export function useAccountsAnalytics(params: {
  apiUrl: string;
  workspaceId: string;
  enabled: boolean;
}) {
  const { apiUrl, workspaceId, enabled } = params;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<
    Array<{
      handle: string;
      follower_count?: number;
      following_count?: number;
      post_count?: number;
      source_key?: string;
    }>
  >([]);

  useEffect(() => {
    if (!enabled) return;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchWorkspaceArtifacts(client, workspaceId, {
          platform: 'instagram',
          playbook_code: 'ig_capture_account_snapshot',
          include_content: true,
          include_preview: false,
          limit: 500,
        });
        if (!response.ok) {
          throw new Error(`Failed to load artifacts: ${response.status}`);
        }
        const data = await response.json();
        const items = (data.artifacts || []).filter(
          (a: any) => (a.metadata || {}).source === 'ig_account_snapshot'
        );

        const byHandle = new Map<string, any>();
        items.forEach((a: any) => {
          const meta = a.metadata || {};
          const c = a.content?.content || a.content || {};
          const handle = meta.target_account_handle || c?.target?.handle;
          if (!handle) return;
          const capturedAt = meta.captured_at || a.created_at || '';
          const existing = byHandle.get(handle);
          const existingAt = existing
            ? ((existing.metadata || {}).captured_at || existing.created_at || '')
            : '';
          if (!existing || capturedAt.localeCompare(existingAt) > 0) {
            byHandle.set(handle, a);
          }
        });

        const nextRows: Array<{
          handle: string;
          follower_count?: number;
          following_count?: number;
          post_count?: number;
          source_key?: string;
        }> = [];
        byHandle.forEach((a: any, handle: string) => {
          const meta = a.metadata || {};
          const c = a.content?.content || a.content || {};
          const p = c.profile || {};
          const sourceKey = meta.source_account_handle
            ? `handle:${meta.source_account_handle}`
            : 'unknown';
          nextRows.push({
            handle,
            follower_count: typeof p.follower_count === 'number' ? p.follower_count : undefined,
            following_count: typeof p.following_count === 'number' ? p.following_count : undefined,
            post_count: typeof p.post_count === 'number' ? p.post_count : undefined,
            source_key: sourceKey,
          });
        });
        setRows(nextRows);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load analytics');
        setRows([]);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [enabled, client, workspaceId]);

  return { loading, error, rows };
}
