'use client';

import React, { useState, useEffect } from 'react';
import { useDataSourceOverlay, DataSourceWithOverlay } from '@/hooks/useDataSourceOverlay';
import DataSourceBindingCard from './DataSourceBindingCard';
import DataSourceBindingModal from './DataSourceBindingModal';
import ConfirmDialog from '@/components/ConfirmDialog';

interface DataSourceOverlayPanelProps {
  workspaceId: string;
}

export default function DataSourceOverlayPanel({ workspaceId }: DataSourceOverlayPanelProps) {
  const {
    dataSources,
    loading,
    error,
    loadDataSources,
    updateDataSourceOverlay,
  } = useDataSourceOverlay(workspaceId);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingDataSource, setEditingDataSource] = useState<DataSourceWithOverlay | null>(null);
  const [deletingDataSource, setDeletingDataSource] = useState<DataSourceWithOverlay | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  useEffect(() => {
    loadDataSources();
  }, [loadDataSources]);

  const handleCreate = () => {
    setEditingDataSource(null);
    setIsModalOpen(true);
  };

  const handleEdit = (dataSource: DataSourceWithOverlay) => {
    setEditingDataSource(dataSource);
    setIsModalOpen(true);
  };

  const handleDelete = (dataSource: DataSourceWithOverlay) => {
    setDeletingDataSource(dataSource);
    setShowDeleteDialog(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingDataSource) return;

    try {
      await updateDataSourceOverlay(deletingDataSource.data_source_id, {
        enabled: false,
      });
      setDeletingDataSource(null);
      setShowDeleteDialog(false);
      await loadDataSources();
    } catch (err) {
      console.error('Failed to delete data source binding:', err);
    }
  };

  const handleModalSave = async (
    dataSourceId: string,
    overlay: {
      access_mode_override?: 'read' | 'write' | 'admin';
      display_name?: string;
      enabled?: boolean;
    }
  ) => {
    try {
      await updateDataSourceOverlay(dataSourceId, overlay);
      setIsModalOpen(false);
      setEditingDataSource(null);
      await loadDataSources();
    } catch (err) {
      console.error('Failed to save data source overlay:', err);
      throw err;
    }
  };

  const handleModalClose = () => {
    setIsModalOpen(false);
    setEditingDataSource(null);
  };

  const boundDataSources = dataSources.filter(ds => ds.overlay_applied);

  if (loading && dataSources.length === 0) {
    return (
      <div className="p-4">
        <div className="text-gray-500 dark:text-gray-400">Loading data sources...</div>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Data Source Overlay Settings
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Manage workspace data source bindings and access controls
            </p>
          </div>
          <button
            onClick={handleCreate}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Add Data Source
          </button>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {boundDataSources.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>No data source bindings configured</p>
            <p className="text-sm mt-2">Click "Add Data Source" to create one</p>
          </div>
        ) : (
          <div className="space-y-3">
            {boundDataSources.map((dataSource) => (
              <DataSourceBindingCard
                key={dataSource.data_source_id}
                dataSource={dataSource}
                onEdit={() => handleEdit(dataSource)}
                onDelete={() => handleDelete(dataSource)}
              />
            ))}
          </div>
        )}

        {dataSources.length > 0 && (
          <div className="mt-6">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
              Available Data Sources
            </h4>
            <div className="space-y-2">
              {dataSources.filter(ds => !ds.overlay_applied).map((dataSource) => (
                <div
                  key={dataSource.data_source_id}
                  className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-3"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {dataSource.display_name || dataSource.data_source_name}
                      </span>
                      <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                        ({dataSource.data_source_type})
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        setEditingDataSource(dataSource);
                        setIsModalOpen(true);
                      }}
                      className="px-3 py-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
                    >
                      Bind
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <DataSourceBindingModal
        isOpen={isModalOpen}
        onClose={handleModalClose}
        onSave={handleModalSave}
        dataSource={editingDataSource}
        availableDataSources={dataSources}
      />

      <ConfirmDialog
        isOpen={showDeleteDialog}
        onClose={() => {
          setShowDeleteDialog(false);
          setDeletingDataSource(null);
        }}
        onConfirm={handleConfirmDelete}
        title="Disable Data Source Binding"
        message={
          deletingDataSource
            ? `Are you sure you want to disable the binding for "${deletingDataSource.display_name || deletingDataSource.data_source_name}"?`
            : ''
        }
        confirmText="Disable"
        cancelText="Cancel"
        confirmButtonClassName="bg-red-600 hover:bg-red-700"
      />
    </>
  );
}

