'use client';

import React, { useState } from 'react';
import Header from '../../../components/Header';
import { MindGraph } from '../../../components/mindscape/MindGraph';
import { GraphControls } from '../../../components/mindscape/GraphControls';
import { NodeDetailPanel } from '../../../components/mindscape/NodeDetailPanel';
import { NodeEditor } from '../../../components/mindscape/NodeEditor';
import { DeleteConfirmDialog } from '../../../components/mindscape/DeleteConfirmDialog';
import { t } from '../../../lib/i18n';
import { GraphNode, useFullGraph, deleteNode, initializeGraph } from '../../../lib/graph-api';
import { OpenWorkspaceDialog } from '../../../components/mindscape/OpenWorkspaceDialog';

export default function GraphPage() {
  const [activeLens, setActiveLens] = useState<'all' | 'direction' | 'action'>('all');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [editingNode, setEditingNode] = useState<GraphNode | undefined>(undefined);
  const [isCreatingNode, setIsCreatingNode] = useState(false);
  const [deletingNodeId, setDeletingNodeId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [openingWorkspaceNode, setOpeningWorkspaceNode] = useState<GraphNode | null>(null);
  const [isInitializing, setIsInitializing] = useState(false);

  const { refresh } = useFullGraph();

  const handleNodeSelect = (nodeId: string, attributes: any) => {
    const node = attributes as GraphNode;
    if (node) {
      setSelectedNode(node);
    }
  };

  const handleOpenWorkspace = (nodeId: string) => {
    const node = selectedNode;
    if (node && node.id === nodeId) {
      setOpeningWorkspaceNode(node);
    }
  };

  const handleEdit = (node: GraphNode) => {
    setSelectedNode(null);
    setEditingNode(node);
  };

  const handleCreate = () => {
    setIsCreatingNode(true);
  };

  const handleSave = async (node: GraphNode) => {
    setEditingNode(undefined);
    setIsCreatingNode(false);
    setSelectedNode(null);
    await refresh();
  };

  const handleCancel = () => {
    setEditingNode(undefined);
    setIsCreatingNode(false);
  };

  const handleDeleteClick = (nodeId: string) => {
    setDeletingNodeId(nodeId);
  };

  const handleDeleteConfirm = async () => {
    if (!deletingNodeId) return;

    setIsDeleting(true);
    try {
      await deleteNode(deletingNodeId);
      setDeletingNodeId(null);
      setSelectedNode(null);
      await refresh();
    } catch (error) {
      console.error('Failed to delete node:', error);
      alert(t('graphNodeDeleteFailed'));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeletingNodeId(null);
  };

  const handleInitialize = async () => {
    setIsInitializing(true);
    try {
      await initializeGraph();
      await refresh();
    } catch (error) {
      console.error('Failed to initialize graph:', error);
      alert(t('graphInitializeFailed'));
    } finally {
      setIsInitializing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              {t('navMindscape')} - {t('graphLensAll')}
            </h1>
            <p className="text-gray-600">
              {t('mindscapePageDescription')}
            </p>
          </div>
          <button
            onClick={handleCreate}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
          >
            {t('graphNodeCreateButton')}
          </button>
        </div>

        <div className="mb-4">
          <GraphControls
            activeLens={activeLens}
            onLensChange={setActiveLens}
          />
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <MindGraph
            activeLens={activeLens}
            onNodeSelect={handleNodeSelect}
            onInitialize={handleInitialize}
          />
        </div>

        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onOpenWorkspace={handleOpenWorkspace}
          onEdit={handleEdit}
          onDelete={handleDeleteClick}
        />

        {(editingNode !== undefined || isCreatingNode) && (
          <NodeEditor
            node={editingNode}
            onSave={handleSave}
            onCancel={handleCancel}
          />
        )}

        {deletingNodeId && (
          <DeleteConfirmDialog
            title={t('graphNodeDeleteTitle')}
            message={t('graphNodeDeleteConfirm')}
            onConfirm={handleDeleteConfirm}
            onCancel={handleDeleteCancel}
            isDeleting={isDeleting}
          />
        )}

        {openingWorkspaceNode && (
          <OpenWorkspaceDialog
            node={openingWorkspaceNode}
            onClose={() => setOpeningWorkspaceNode(null)}
          />
        )}
      </main>
    </div>
  );
}

