'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { CheckCircle2, FolderOpen, RefreshCw, Search, XCircle } from 'lucide-react';
import type { IGPost } from '../types';

type VaultAction = 'validate' | 'init' | 'scan';
type PostType = 'post' | 'carousel' | 'reel' | 'story';

function normalizePath(p: string): string {
  return (p || '').replace(/\\/g, '/').trim();
}

function derivePostFolderFromPostPath(postPath: string): string {
  const p = normalizePath(postPath);
  if (!p) return '';

  let rel = p;
  const idx = rel.lastIndexOf('/posts/');
  if (idx >= 0) rel = rel.slice(idx + '/posts/'.length);
  rel = rel.replace(/^\/+/, '').replace(/\/+$/, '');

  // If pointing to a file, use its parent folder.
  if (rel.endsWith('.md') && rel.includes('/')) {
    rel = rel.slice(0, rel.lastIndexOf('/'));
  }

  // If still has nested parts, keep the first folder segment (most vaults use one folder per post).
  if (rel.includes('/')) {
    rel = rel.split('/')[0] || rel;
  }

  return rel;
}

function safeJson(value: any): string {
  try {
    return JSON.stringify(value ?? null, null, 2);
  } catch {
    return String(value ?? '');
  }
}

export default function AssetsPanel(props: {
  workspaceId: string;
  apiUrl: string;
  posts: IGPost[];
  selectedPostId: string | null;
  onPostSelect: (postId: string | null) => void;
}) {
  const { workspaceId, apiUrl, posts, selectedPostId, onPostSelect } = props;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);

  const selectedPost = useMemo(() => {
    if (!selectedPostId) return null;
    return posts.find((p) => p.id === selectedPostId) || null;
  }, [posts, selectedPostId]);

  const selectedPostFolder = useMemo(() => {
    return selectedPost?.post_path ? derivePostFolderFromPostPath(selectedPost.post_path) : '';
  }, [selectedPost?.post_path]);

  const [loading, setLoading] = useState(false);
  const [vaultAction, setVaultAction] = useState<VaultAction>('validate');
  const [createMissing, setCreateMissing] = useState(false);
  const [vaultResult, setVaultResult] = useState<any | null>(null);
  const [vaultError, setVaultError] = useState<string | null>(null);

  const [postFolder, setPostFolder] = useState('');
  const [postType, setPostType] = useState<PostType>('post');
  const [assetResult, setAssetResult] = useState<any | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);

  useEffect(() => {
    if (!postFolder && selectedPostFolder) {
      setPostFolder(selectedPostFolder);
    }
  }, [postFolder, selectedPostFolder]);

  const runVault = async () => {
    setLoading(true);
    setVaultError(null);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_vault_structure_manager',
        inputs: {
          workspace_id: workspaceId,
          action: vaultAction,
          create_missing: createMissing,
        },
        execution_mode: 'sync',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Vault action failed: ${response.status}`);
      }
      const data = await response.json();
      setVaultResult(data.result || data);
    } catch (e) {
      setVaultError(e instanceof Error ? e.message : 'Vault action failed');
      setVaultResult(null);
    } finally {
      setLoading(false);
    }
  };

  const runAssetManager = async (action: 'scan' | 'validate' | 'generate_list') => {
    const folder = (postFolder || '').trim();
    if (!folder) {
      alert('Please input post_folder (e.g. 2026-01-20_my-post)');
      return;
    }
    setLoading(true);
    setAssetError(null);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_asset_manager',
        inputs: {
          workspace_id: workspaceId,
          post_folder: folder,
          post_type: postType,
        },
        execution_mode: 'sync',
      });
      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Asset manager failed: ${response.status}`);
      }
      const data = await response.json();
      setAssetResult(data.result || data);
    } catch (e) {
      setAssetError(e instanceof Error ? e.message : 'Asset manager failed');
      setAssetResult(null);
    } finally {
      setLoading(false);
    }
  };

  const vaultOk = vaultResult?.is_valid === true;
  const vaultHasResult = vaultResult !== null;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <FolderOpen className="w-5 h-5 text-orange-600 dark:text-orange-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Assets</h2>
        </div>
        <button
          onClick={() => {
            void runVault();
          }}
          disabled={loading}
          className="text-xs text-blue-600 hover:underline flex items-center gap-1 disabled:opacity-50"
          title="Validate vault structure"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          Quick Validate
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold text-gray-900 dark:text-gray-100">Vault Structure</div>
            {vaultHasResult && (
              <div className="flex items-center gap-1 text-xs">
                {vaultOk ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
                    <span className="text-green-700 dark:text-green-300">Valid</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                    <span className="text-red-700 dark:text-red-300">Needs Attention</span>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2 mb-3">
            <div className="grid grid-cols-[140px,1fr] items-center gap-2">
              <div className="text-xs text-gray-600 dark:text-gray-400">Action</div>
              <select
                value={vaultAction}
                onChange={(e) => setVaultAction(e.target.value as VaultAction)}
                className="px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="validate">validate</option>
                <option value="init">init</option>
                <option value="scan">scan</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={createMissing}
                onChange={(e) => setCreateMissing(e.target.checked)}
                className="rounded"
              />
              create_missing (validate only)
            </label>

            <button
              onClick={() => void runVault()}
              disabled={loading}
              className="w-full px-3 py-2 text-sm rounded bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-50"
            >
              Run
            </button>
          </div>

          {vaultError && (
            <div className="text-xs text-red-600 dark:text-red-400 mb-2 whitespace-pre-wrap">{vaultError}</div>
          )}

          {vaultResult && (
            <div className="space-y-2">
              <div className="text-xs text-gray-600 dark:text-gray-400">
                <div><strong>Status:</strong> {String(vaultResult.structure_status || '')}</div>
                {Array.isArray(vaultResult.missing_folders) && vaultResult.missing_folders.length > 0 && (
                  <div className="mt-1">
                    <strong>Missing:</strong> {vaultResult.missing_folders.join(', ')}
                  </div>
                )}
                {Array.isArray(vaultResult.created_folders) && vaultResult.created_folders.length > 0 && (
                  <div className="mt-1">
                    <strong>Created:</strong> {vaultResult.created_folders.join(', ')}
                  </div>
                )}
                {(vaultResult.post_count !== undefined || vaultResult.series_count !== undefined || vaultResult.idea_count !== undefined) && (
                  <div className="mt-1">
                    <strong>Scan:</strong>{' '}
                    posts={vaultResult.post_count ?? '-'} series={vaultResult.series_count ?? '-'} ideas={vaultResult.idea_count ?? '-'}
                  </div>
                )}
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer text-blue-600 dark:text-blue-400 hover:underline">Raw result</summary>
                <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                  {safeJson(vaultResult)}
                </pre>
              </details>
            </div>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold text-gray-900 dark:text-gray-100">Asset Manager</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">naming / size / format</div>
          </div>

          <div className="space-y-2 mb-3">
            <div className="grid grid-cols-[140px,1fr] items-center gap-2">
              <div className="text-xs text-gray-600 dark:text-gray-400">Post</div>
              <select
                value={selectedPostId || ''}
                onChange={(e) => onPostSelect(e.target.value || null)}
                className="px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="">(optional) Select a post</option>
                {posts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {(p.post_path || p.id).toString().slice(-60)}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-[140px,1fr] items-center gap-2">
              <div className="text-xs text-gray-600 dark:text-gray-400">post_folder</div>
              <input
                type="text"
                value={postFolder}
                onChange={(e) => setPostFolder(e.target.value)}
                className="px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                placeholder="2026-01-20_post-slug"
              />
            </div>

            <div className="grid grid-cols-[140px,1fr] items-center gap-2">
              <div className="text-xs text-gray-600 dark:text-gray-400">post_type</div>
              <select
                value={postType}
                onChange={(e) => setPostType(e.target.value as PostType)}
                className="px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
              >
                <option value="post">post</option>
                <option value="carousel">carousel</option>
                <option value="reel">reel</option>
                <option value="story">story</option>
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1">
              <button
                onClick={() => void runAssetManager('scan')}
                disabled={loading}
                className="px-3 py-2 text-sm rounded bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Search className="w-4 h-4" />
                Scan
              </button>
              <button
                onClick={() => void runAssetManager('validate')}
                disabled={loading}
                className="px-3 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Validate
              </button>
              <button
                onClick={() => void runAssetManager('generate_list')}
                disabled={loading}
                className="px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
              >
                Required list
              </button>
            </div>
          </div>

          {assetError && (
            <div className="text-xs text-red-600 dark:text-red-400 mb-2 whitespace-pre-wrap">{assetError}</div>
          )}

          {assetResult && (
            <div className="space-y-2">
              <details className="text-xs" open>
                <summary className="cursor-pointer text-gray-700 dark:text-gray-200">Summary</summary>
                <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                  {Array.isArray(assetResult.missing_assets) && (
                    <div><strong>Missing assets:</strong> {assetResult.missing_assets.length}</div>
                  )}
                  {Array.isArray(assetResult.size_warnings) && (
                    <div><strong>Size warnings:</strong> {assetResult.size_warnings.length}</div>
                  )}
                  {assetResult.spec_used && (
                    <div><strong>Spec:</strong> {String(assetResult.spec_used)}</div>
                  )}
                </div>
              </details>

              <details className="text-xs">
                <summary className="cursor-pointer text-blue-600 dark:text-blue-400 hover:underline">Raw result</summary>
                <pre className="mt-2 bg-gray-100 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                  {safeJson(assetResult)}
                </pre>
              </details>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

