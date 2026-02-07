'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { t } from '@/lib/i18n';
import { bindLensToWorkspace, useFullGraph, createLensProfile } from '@/lib/graph-api';
import { GraphNode } from '@/lib/graph-api';

interface OpenWorkspaceDialogProps {
  node: GraphNode;
  onClose: () => void;
}

export function OpenWorkspaceDialog({ node, onClose }: OpenWorkspaceDialogProps) {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState('');
  const [isBinding, setIsBinding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { refresh } = useFullGraph();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspaceId.trim()) return;

    setError(null);
    setIsBinding(true);

    try {
      const lensName = `Lens: ${node.label}`;
      const lens = await createLensProfile({
        name: lensName,
        description: `Lens created from node: ${node.label}`,
        is_default: false,
        active_node_ids: [node.id],
      });

      await bindLensToWorkspace(lens.id, workspaceId.trim());
      await refresh();
      router.push(`/workspaces/${workspaceId.trim()}`);
    } catch (err: any) {
      setError(err.message || t('error' as any));
    } finally {
      setIsBinding(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          {t('graphNodeOpenWorkspaceTitle' as any)}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('graphNodeWorkspaceIdLabel' as any)}
            </label>
            <input
              type="text"
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
              placeholder={t('graphNodeWorkspaceIdPlaceholder' as any)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              required
            />
            <p className="mt-1 text-xs text-gray-500">
              {t('graphNodeWorkspaceIdHint' as any)}
            </p>
          </div>

          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              disabled={isBinding}
            >
              {t('cancel' as any)}
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isBinding || !workspaceId.trim()}
            >
              {isBinding ? t('binding' as any) : t('open' as any)}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

