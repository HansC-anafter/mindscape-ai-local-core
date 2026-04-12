import { useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { ConnectedAccount, DiscoveredAccount } from '../types';
import { applyExecutionBackendHint, executePlaybookStart, fetchWorkspaceArtifacts } from '../api';

type SelectedAccount = ConnectedAccount | DiscoveredAccount | null;

export function useAccountSnapshots(params: {
  apiUrl: string;
  workspaceId: string;
  selectedAccount: SelectedAccount;
  browserProfilePath: string;

  onAfterCapture: () => void;
  onRefreshSelectedAccount?: () => void;
}) {
  const {
    apiUrl,
    workspaceId,
    selectedAccount,
    browserProfilePath,
    onAfterCapture,
    onRefreshSelectedAccount,
  } = params;

  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [snapshotCompareIds, setSnapshotCompareIds] = useState<string[]>([]);
  const [snapshotHandleInput, setSnapshotHandleInput] = useState<string>('');

  useEffect(() => {
    if (!selectedAccount || ('channel_config_id' in selectedAccount)) {
      setSnapshots([]);
      setSnapshotCompareIds([]);
      setSnapshotError(null);
      return;
    }

    const handle = (selectedAccount as DiscoveredAccount).handle;
    setSnapshotHandleInput(handle);
    setSnapshotCompareIds([]);

    const load = async () => {
      setSnapshotsLoading(true);
      setSnapshotError(null);
      try {
        const response = await fetchWorkspaceArtifacts(client, workspaceId, {
          platform: 'instagram',
          playbook_code: 'ig_capture_account_snapshot',
          include_content: true,
          include_preview: false,
          limit: 200,
        });
        if (!response.ok) {
          throw new Error(`Failed to load artifacts: ${response.status}`);
        }
        const data = await response.json();
        const items = (data.artifacts || []).filter((a: any) => {
          const meta = a.metadata || {};
          if (meta.source !== 'ig_account_snapshot') return false;
          if (meta.target_account_handle && meta.target_account_handle === handle) return true;
          const c = a.content?.content || a.content || {};
          return c?.target?.handle === handle;
        });
        items.sort((a: any, b: any) => {
          const ma = a.metadata || {};
          const mb = b.metadata || {};
          const ta = ma.captured_at || a.created_at || '';
          const tb = mb.captured_at || b.created_at || '';
          return tb.localeCompare(ta);
        });
        setSnapshots(items);
      } catch (e) {
        setSnapshotError(e instanceof Error ? e.message : 'Failed to load snapshots');
        setSnapshots([]);
      } finally {
        setSnapshotsLoading(false);
      }
    };

    load();
  }, [selectedAccount, client, workspaceId]);

  const captureSnapshot = async (handle: string) => {
    const trimmed = (handle || '').trim().replace(/^@/, '');
    if (!trimmed) return;

    setSnapshotsLoading(true);
    setSnapshotError(null);
    try {
      const params = new URLSearchParams({
        playbook_code: 'ig_capture_account_snapshot',
        profile_id: 'default-user',
        workspace_id: workspaceId,
        auto_execute: 'true',
      });
      applyExecutionBackendHint(params, workspaceId);
      const response = await executePlaybookStart(client, params, {
        inputs: {
          target_account_handle: trimmed,
          workspace_id: workspaceId,
          user_data_dir: browserProfilePath,
        },
        target_language: 'en',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Snapshot failed: ${response.status}`);
      }
      await response.json();
      setTimeout(() => {
        onAfterCapture();
        onRefreshSelectedAccount?.();
      }, 2500);
    } catch (e) {
      setSnapshotError(e instanceof Error ? e.message : 'Snapshot failed');
    } finally {
      setTimeout(() => setSnapshotsLoading(false), 1200);
    }
  };

  return {
    snapshots,
    snapshotsLoading,
    snapshotError,
    snapshotCompareIds,
    setSnapshotCompareIds,
    snapshotHandleInput,
    setSnapshotHandleInput,
    captureSnapshot,
  };
}
