'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';
import { GraphNode, unlinkNodeFromPlaybook, useFullGraph } from '@/lib/graph-api';
import { PlaybookLinkDialog } from './PlaybookLinkDialog';

interface NodeDetailPanelProps {
  node: GraphNode | null;
  onClose: () => void;
  onOpenWorkspace: (nodeId: string) => void;
  onEdit: (node: GraphNode) => void;
  onDelete: (nodeId: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  value: t('graphNodeTypeValue'),
  worldview: t('graphNodeTypeWorldview'),
  aesthetic: t('graphNodeTypeAesthetic'),
  knowledge: t('graphNodeTypeKnowledge'),
  strategy: t('graphNodeTypeStrategy'),
  role: t('graphNodeTypeRole'),
  rhythm: t('graphNodeTypeRhythm'),
};

export function NodeDetailPanel({
  node,
  onClose,
  onOpenWorkspace,
  onEdit,
  onDelete,
}: NodeDetailPanelProps) {
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const { refresh } = useFullGraph();

  if (!node) return null;

  const handleEdit = () => {
    onEdit(node);
  };

  const handleDelete = () => {
    if (confirm(t('graphNodeDeleteConfirm'))) {
      onDelete(node.id);
    }
  };

  const handleLinkPlaybook = async (playbookCode: string) => {
    setShowLinkDialog(false);
    await refresh();
  };

  const handleUnlinkPlaybook = async (playbookCode: string) => {
    if (confirm(t('graphNodeUnlinkPlaybookConfirm'))) {
      try {
        await unlinkNodeFromPlaybook(node.id, playbookCode);
        await refresh();
      } catch (error) {
        alert(t('graphNodeUnlinkPlaybookFailed'));
      }
    }
  };

  return (
    <div className="fixed right-0 top-0 h-full w-96 bg-white shadow-xl border-l border-gray-200 z-50 overflow-y-auto">
      <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-900">{node.label}</h3>
        <button
          onClick={onClose}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          aria-label={t('close')}
        >
          ✕
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div>
          <span className="text-xs text-gray-500">{t('graphNodeTypeLabel')}</span>
          <div className="mt-1">
            <span className="px-3 py-1 bg-indigo-100 text-indigo-800 rounded-full text-sm">
              {TYPE_LABELS[node.node_type] || node.node_type}
            </span>
            <span className="ml-2 px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-sm">
              {node.category === 'direction' ? t('graphLensDirection') : t('graphLensAction')}
            </span>
          </div>
        </div>

        {node.description && (
          <div>
            <span className="text-xs text-gray-500">{t('graphNodeDescriptionLabel')}</span>
            <p className="mt-1 text-gray-700">{node.description}</p>
          </div>
        )}

        {node.content && (
          <div>
            <span className="text-xs text-gray-500">{t('graphNodeContentLabel')}</span>
            <p className="mt-1 text-gray-700 whitespace-pre-wrap">{node.content}</p>
          </div>
        )}

        <div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-gray-500">{t('graphNodeLinkedPlaybooksLabel')}</span>
            <button
              onClick={() => setShowLinkDialog(true)}
              className="text-xs text-indigo-600 hover:underline"
            >
              {t('graphNodeAddPlaybookLink')}
            </button>
          </div>
          <div className="mt-2 space-y-2">
            {node.linked_playbook_codes?.length ? (
              node.linked_playbook_codes.map((pb) => (
                <div
                  key={pb}
                  className="p-2 bg-gray-50 rounded-lg flex items-center justify-between"
                >
                  <span className="text-sm text-gray-700">📋 {pb}</span>
                  <button
                    onClick={() => handleUnlinkPlaybook(pb)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    {t('remove')}
                  </button>
                </div>
              ))
            ) : (
              <p className="text-sm text-gray-400">{t('graphNodeNoLinkedPlaybooks')}</p>
            )}
          </div>
        </div>

        {showLinkDialog && (
          <PlaybookLinkDialog
            nodeId={node.id}
            onLink={handleLinkPlaybook}
            onCancel={() => setShowLinkDialog(false)}
          />
        )}

        <div className="pt-4 border-t border-gray-200 space-y-2">
          <button
            onClick={() => onOpenWorkspace(node.id)}
            className="w-full py-2 px-4 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            {t('graphNodeOpenWorkspaceButton')}
          </button>
          <button
            onClick={handleEdit}
            className="w-full py-2 px-4 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            {t('graphNodeEditButton')}
          </button>
          <button
            onClick={handleDelete}
            className="w-full py-2 px-4 bg-red-50 text-red-700 rounded-lg hover:bg-red-100 transition-colors"
          >
            {t('graphNodeDeleteButton')}
          </button>
        </div>
      </div>
    </div>
  );
}

