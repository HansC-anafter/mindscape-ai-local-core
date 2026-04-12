'use client';

/**
 * Publish Panel
 *
 * Features:
 * - Account selection panel (Connected accounts list)
 * - Publish queue view
 * - Schedule management
 * - Authorization status display
 */

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { parseServerTimestamp, formatLocalDateTime } from '@/lib/time';
import { Upload, Clock, CheckCircle2, XCircle, Calendar, AlertCircle } from 'lucide-react';
import type { IGPost } from '../types';

interface PublishPanelProps {
  workspaceId: string;
  apiUrl: string;
  selectedPostId: string | null;
  posts: IGPost[];
  onPostSelect: (postId: string) => void;
}

interface ConnectedAccount {
  channel_config_id: number;
  channel_name: string;
  channel_type: 'instagram';
  status: 'connected' | 'expired' | 'insufficient_permissions';
  expires_at?: string;
  permissions: string[];
  reauth_url?: string;
  page_id?: string;
  username?: string;
}

interface PublishQueue {
  post_path: string;
  scheduled_time?: string;
  channel_config_id: number;
  status: 'pending' | 'scheduled' | 'published' | 'failed';
  published_at?: string;
}

export default function PublishPanel({
  workspaceId,
  apiUrl,
  selectedPostId,
  posts,
  onPostSelect
}: PublishPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [publishQueue, setPublishQueue] = useState<PublishQueue[]>([]);
  const [loading, setLoading] = useState(false);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [scheduledTime, setScheduledTime] = useState('');

  const [syncContentType, setSyncContentType] = useState<'posts' | 'reels' | 'stories' | 'all'>('all');
  const [syncMediaType, setSyncMediaType] = useState<'IMAGE' | 'VIDEO' | 'CAROUSEL_ALBUM' | ''>('');
  const [syncLimit, setSyncLimit] = useState<number>(25);
  const [syncSince, setSyncSince] = useState<string>('');
  const [syncUntil, setSyncUntil] = useState<string>('');
  const [syncTriggerOpenSeo, setSyncTriggerOpenSeo] = useState<boolean>(false);
  const [syncResult, setSyncResult] = useState<any | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    loadConnectedAccounts();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    loadPublishQueue();
  }, [workspaceId, apiUrl]);

  const loadConnectedAccounts = async () => {
    setLoading(true);
    try {
      // Channel bindings managed by mindscape_cloud_integration capability pack
      const response = await client.get(
        `/api/v1/capabilities/mindscape_cloud_integration/channel-bindings?workspace_id=${workspaceId}`
      );

      if (!response.ok) {
        setAccounts([]);
        return;
      }

      const data = await response.json();
      // Filter to instagram channel bindings
      const igBindings = (data.bindings || []).filter(
        (b: any) => b.channel_type === 'instagram'
      );
      const accounts: ConnectedAccount[] = igBindings.map((binding: any) => ({
        channel_config_id: binding.channel_id || binding.id,
        channel_name: binding.channel_name || binding.channel_id || `Channel ${binding.id}`,
        channel_type: 'instagram',
        status: binding.status === 'active' ? 'connected' : 'expired',
        expires_at: undefined,
        permissions: [],
        reauth_url: undefined,
        page_id: undefined,
        username: binding.channel_name
      }));

      setAccounts(accounts);
    } catch (err) {
      console.error('Failed to load connected accounts:', err);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  };

  const loadPublishQueue = async () => {
    setLoading(true);
    try {
      const [artifactsResponse, executionsResponse] = await Promise.all([
        client.get(
          `/api/v1/workspaces/${workspaceId}/artifacts?platform=instagram&include_content=false&include_preview=false&limit=100`
        ),
        client.get(
          `/api/v1/workspaces/${workspaceId}/executions?playbook_code=ig_publish_content&limit=50&order_by=created_at&order=desc`
        )
      ]);

      const queue: PublishQueue[] = [];

      if (artifactsResponse.ok) {
        const artifactsData = await artifactsResponse.json();
        (artifactsData.artifacts || []).forEach((artifact: any) => {
          const metadata = artifact.metadata || {};
          const frontmatter = metadata.frontmatter || {};

          const status = metadata.status || frontmatter.status || 'draft';
          const scheduledTime = metadata.scheduled_time || frontmatter.scheduled_time;
          const channelConfigId = metadata.channel_config_id || frontmatter.channel_config_id;

          if (status === 'scheduled' || status === 'published' || scheduledTime) {
            queue.push({
              post_path: metadata.post_path || artifact.storage_path || artifact.id,
              scheduled_time: scheduledTime,
              channel_config_id: channelConfigId || 0,
              status: status === 'published' ? 'published' :
                status === 'scheduled' ? 'scheduled' :
                  scheduledTime ? 'scheduled' : 'pending',
              published_at: status === 'published' ? (artifact.updated_at || artifact.created_at) : undefined
            });
          }
        });
      }

      if (executionsResponse.ok) {
        const executionsData = await executionsResponse.json();
        (executionsData.executions || []).forEach((exec: any) => {
          if (exec.status === 'completed' && exec.result) {
            const result = exec.result || {};
            const inputs = exec.inputs || {};
            const postPath = result.post_path || inputs.post_path;

            const existingIndex = queue.findIndex(q => q.post_path === postPath);
            if (existingIndex >= 0) {
              queue[existingIndex].status = 'published';
              queue[existingIndex].published_at = exec.completed_at || exec.updated_at;
            } else if (postPath) {
              queue.push({
                post_path: postPath,
                scheduled_time: inputs.scheduled_publish_time,
                channel_config_id: inputs.channel_config_id || 0,
                status: exec.status === 'completed' ? 'published' : 'pending',
                published_at: exec.completed_at || exec.updated_at
              });
            }
          }
        });
      }

      setPublishQueue(queue);
    } catch (err) {
      console.error('Failed to load publish queue:', err);
      setPublishQueue([]);
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (immediate: boolean = false) => {
    if (!selectedPostId) {
      alert('Please select a post first');
      return;
    }

    if (!selectedAccountId) {
      alert('Please select an account first');
      return;
    }

    setLoading(true);
    try {
      const post = posts.find(p => p.id === selectedPostId);
      if (!post) {
        throw new Error('Selected post does not exist');
      }

      const inputs: any = {
        workspace_id: workspaceId,
        channel_config_id: selectedAccountId,
        media_type: 'photo', // TODO: Get from post frontmatter
        media_path: post.frontmatter?.media_path || '',
        caption: post.frontmatter?.caption || post.content || post.text || '',
        post_id: post.post_id || post.artifact_id
      };

      if (!immediate && scheduledTime) {
        inputs.scheduled_publish_time = scheduledTime;
      }

      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_publish_content',
        inputs: inputs,
        execution_mode: 'async'
      });

      if (response.ok) {
        const data = await response.json();
        await loadPublishQueue();
        setShowScheduleDialog(false);
        setScheduledTime('');
        alert(immediate ? 'Published successfully!' : 'Added to schedule!');
      } else {
        const error = await response.json();
        alert(`Publish failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to publish:', err);
      alert(`Publish failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const toDateTimeLocalInputValue = (date: Date): string => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${d}T${hh}:${mm}`;
  };

  const selectedAccount = accounts.find(a => a.channel_config_id === selectedAccountId);

  const handleSyncContent = async () => {
    if (!selectedAccountId) {
      alert('Please select an account first');
      return;
    }

    setLoading(true);
    setSyncError(null);
    try {
      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_sync_content',
        inputs: {
          channel_config_id: selectedAccountId,
          workspace_id: workspaceId,
          content_type: syncContentType,
          media_type: syncContentType === 'posts' && syncMediaType ? syncMediaType : undefined,
          limit: syncLimit,
          since: (syncSince || '').trim() || undefined,
          until: (syncUntil || '').trim() || undefined,
          trigger_openseo: syncTriggerOpenSeo,
        },
        execution_mode: 'sync',
      });

      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Sync failed: ${response.status}`);
      }

      const data = await response.json();
      setSyncResult(data.result || data);
      await loadPublishQueue();
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Sync failed');
      setSyncResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          Publish Management
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4">
        {/* Selected post info */}
        {selectedPostId && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
            <div className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-1">
              Selected Post
            </div>
            <div className="text-xs text-blue-700 dark:text-blue-300 truncate">
              {posts.find(p => p.id === selectedPostId)?.text?.substring(0, 50) || selectedPostId}
            </div>
          </div>
        )}

        {/* Account selection */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Select Account
          </h3>
          {loading ? (
            <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
              Loading accounts...
            </div>
          ) : accounts.length === 0 ? (
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-yellow-600 dark:text-yellow-400 mt-0.5" />
                <div className="flex-1">
                  <p className="text-xs font-semibold text-yellow-900 dark:text-yellow-100 mb-1">
                    No Connected Accounts Found
                  </p>
                  <p className="text-xs text-yellow-700 dark:text-yellow-300">
                    Please complete Instagram OAuth authorization in site-hub first
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {accounts.map((account) => (
                <div
                  key={account.channel_config_id}
                  onClick={() => setSelectedAccountId(account.channel_config_id)}
                  className={`p-3 rounded-lg border cursor-pointer transition-colors ${selectedAccountId === account.channel_config_id
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                    }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {account.channel_name}
                    </span>
                    <span className={`px-2 py-0.5 text-xs rounded ${account.status === 'connected' ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' :
                      account.status === 'expired' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400' :
                        'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'
                      }`}>
                      {account.status === 'connected' ? 'Connected' :
                        account.status === 'expired' ? 'Expired' :
                          'Insufficient Permissions'}
                    </span>
                  </div>
                  {account.status !== 'connected' && account.reauth_url && (
                    <a
                      href={account.reauth_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1 block"
                    >
                      Reauthorize
                    </a>
                  )}
                  {account.permissions.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {account.permissions.map((perm, index) => (
                        <span
                          key={index}
                          className="px-1.5 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
                        >
                          {perm === 'publish' ? 'Publish' :
                            perm === 'schedule' ? 'Schedule' :
                              perm === 'insights' ? 'Insights' :
                                perm}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sync content */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Sync Content
            </h3>
            <button
              onClick={() => void handleSyncContent()}
              disabled={loading || !selectedAccountId || selectedAccount?.status !== 'connected'}
              className="px-3 py-1.5 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
              title="Fetch posts/reels/stories into workspace"
            >
              Sync
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">content_type</div>
              <select
                value={syncContentType}
                onChange={(e) => setSyncContentType(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="all">all</option>
                <option value="posts">posts</option>
                <option value="reels">reels</option>
                <option value="stories">stories</option>
              </select>
            </div>

            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">limit</div>
              <input
                type="number"
                min={1}
                max={100}
                value={syncLimit}
                onChange={(e) => setSyncLimit(Number(e.target.value || 0))}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              />
            </div>

            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">since (ISO 8601)</div>
              <input
                type="text"
                value={syncSince}
                onChange={(e) => setSyncSince(e.target.value)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                placeholder="2024-01-01T00:00:00Z"
              />
            </div>

            <div>
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">until (ISO 8601)</div>
              <input
                type="text"
                value={syncUntil}
                onChange={(e) => setSyncUntil(e.target.value)}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                placeholder="2024-12-31T23:59:59Z"
              />
            </div>

            <div className="sm:col-span-2">
              <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
                media_type (posts only, optional)
              </div>
              <select
                value={syncMediaType}
                onChange={(e) => setSyncMediaType(e.target.value as any)}
                disabled={syncContentType !== 'posts'}
                className="w-full px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700 disabled:opacity-50"
              >
                <option value="">(no filter)</option>
                <option value="IMAGE">IMAGE</option>
                <option value="VIDEO">VIDEO</option>
                <option value="CAROUSEL_ALBUM">CAROUSEL_ALBUM</option>
              </select>
            </div>

            <label className="sm:col-span-2 flex items-center gap-2 text-xs text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={syncTriggerOpenSeo}
                onChange={(e) => setSyncTriggerOpenSeo(e.target.checked)}
                className="rounded"
              />
              trigger_openseo
            </label>
          </div>

          {syncError && (
            <div className="mt-3 text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap">{syncError}</div>
          )}

          {syncResult && (
            <details className="mt-3 text-xs" open>
              <summary className="cursor-pointer text-gray-700 dark:text-gray-200">
                Sync result (raw)
              </summary>
              <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(syncResult, null, 2)}
              </pre>
            </details>
          )}
        </div>

        {/* Publish actions */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Publish Actions
          </h3>
          <div className="space-y-2">
            <button
              onClick={() => handlePublish(true)}
              disabled={loading || !selectedPostId || !selectedAccountId || selectedAccount?.status !== 'connected'}
              className="w-full px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Upload className="w-4 h-4" />
              Publish Now
            </button>
            <button
              onClick={() => setShowScheduleDialog(true)}
              disabled={loading || !selectedPostId || !selectedAccountId || selectedAccount?.status !== 'connected'}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Clock className="w-4 h-4" />
              Schedule Publish
            </button>
          </div>
        </div>

        {/* Schedule dialog */}
        {showScheduleDialog && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-md w-full mx-4">
              <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
                Schedule Publish
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
                    Publish Time
                  </label>
                  <input
                    type="datetime-local"
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                    min={toDateTimeLocalInputValue(new Date())}
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Note: Only photo type supports delayed publish (up to 6 months)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handlePublish(false)}
                    disabled={loading || !scheduledTime}
                    className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    <Clock className="w-4 h-4" />
                    Confirm Schedule
                  </button>
                  <button
                    onClick={() => {
                      setShowScheduleDialog(false);
                      setScheduledTime('');
                    }}
                    className="flex-1 px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Publish queue */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Publish Queue
          </h3>
          <div className="space-y-2">
            {publishQueue.length === 0 ? (
              <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
                No publish queue
              </div>
            ) : (
              publishQueue.map((item, index) => (
                <div
                  key={index}
                  className="p-3 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {item.post_path}
                    </span>
                    <span className={`px-2 py-0.5 text-xs rounded ${item.status === 'published' ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' :
                      item.status === 'failed' ? 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' :
                        item.status === 'scheduled' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' :
                          'bg-gray-100 text-gray-800 dark:bg-gray-600 dark:text-gray-300'
                      }`}>
                      {item.status === 'published' ? 'Published' :
                        item.status === 'failed' ? 'Failed' :
                          item.status === 'scheduled' ? 'Scheduled' :
                            'Pending'}
                    </span>
                  </div>
                  {item.scheduled_time && (
                    <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mt-1">
                      <Calendar className="w-3 h-3" />
                      {formatLocalDateTime(item.scheduled_time)}
                    </div>
                  )}
                  {item.published_at && (
                    <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 mt-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Published at: {formatLocalDateTime(item.published_at)}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
