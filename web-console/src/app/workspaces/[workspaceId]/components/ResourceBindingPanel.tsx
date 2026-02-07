'use client';

import React, { useState } from 'react';
import { useResourceBindings, WorkspaceResourceBinding, CreateResourceBindingRequest } from '@/hooks/useResourceBindings';
import ResourceBindingCard from './ResourceBindingCard';
import ResourceBindingModal from './ResourceBindingModal';
import ConfirmDialog from '@/components/ConfirmDialog';
import { t } from '@/lib/i18n';

interface ResourceBindingPanelProps {
  workspaceId: string;
}

export default function ResourceBindingPanel({ workspaceId }: ResourceBindingPanelProps) {
  const {
    bindings,
    loading,
    error,
    loadBindings,
    createBinding,
    updateBinding,
    deleteBinding,
  } = useResourceBindings(workspaceId);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBinding, setEditingBinding] = useState<WorkspaceResourceBinding | null>(null);
  const [deletingBinding, setDeletingBinding] = useState<WorkspaceResourceBinding | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const handleCreate = () => {
    setEditingBinding(null);
    setIsModalOpen(true);
  };

  const handleEdit = (binding: WorkspaceResourceBinding) => {
    setEditingBinding(binding);
    setIsModalOpen(true);
  };

  const handleDelete = (binding: WorkspaceResourceBinding) => {
    setDeletingBinding(binding);
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingBinding) return;

    try {
      await deleteBinding(deletingBinding.resource_type, deletingBinding.resource_id);
      setDeletingBinding(null);
      setShowDeleteDialog(false);
    } catch (err) {
      console.error('Failed to delete binding:', err);
    }
  };

  const handleModalSave = async (data: CreateResourceBindingRequest) => {
    try {
      if (editingBinding) {
        await updateBinding(editingBinding.resource_type, editingBinding.resource_id, {
          access_mode: data.access_mode,
          overrides: data.overrides,
        });
      } else {
        await createBinding(data);
      }
      setIsModalOpen(false);
      setEditingBinding(null);
    } catch (err) {
      console.error('Failed to save binding:', err);
      throw err;
    }
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
    setEditingBinding(null);
  };

  if (loading && bindings.length === 0) {
    return (
      <div className="p-4">
        <div className="text-gray-500 dark:text-gray-400">Loading resource bindings...</div>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('resourceBindings' as any)}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t('resourceBindingsDescription' as any)}
            </p>
          </div>
          <button
            onClick={handleCreate}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            {t('addBinding' as any)}
          </button>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {bindings.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>{t('noResourceBindings' as any)}</p>
            <p className="text-sm mt-2">{t('noResourceBindingsDescription' as any)}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {bindings.map((binding) => (
              <ResourceBindingCard
                key={`${binding.resource_type}-${binding.resource_id}`}
                binding={binding}
                onEdit={() => handleEdit(binding)}
                onDelete={() => handleDelete(binding)}
              />
            ))}
          </div>
        )}
      </div>

      <ResourceBindingModal
        isOpen={isModalOpen}
        onClose={handleModalClose}
        onSave={handleModalSave}
        binding={editingBinding}
      />

      <ConfirmDialog
        isOpen={showDeleteDialog}
        onClose={() => {
          setShowDeleteDialog(false);
          setDeletingBinding(null);
        }}
        onConfirm={handleConfirmDelete}
        title={t('deleteResourceBinding' as any)}
        message={
          deletingBinding
            ? t('deleteResourceBindingConfirm', {
                resourceType: deletingBinding.resource_type,
                resourceId: deletingBinding.resource_id,
              })
            : ''
        }
        confirmText={t('delete' as any)}
        cancelText={t('cancel' as any)}
        confirmButtonClassName="bg-red-600 hover:bg-red-700"
      />
    </>
  );
}

