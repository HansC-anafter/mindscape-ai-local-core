'use client';

import React, { useState } from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { StatusPill } from './StatusPill';

interface MCPServer {
  id: string;
  name: string;
  transport: 'stdio' | 'http';
  status: 'connected' | 'disconnected' | 'error';
  tools_count?: number;
  last_connected?: string;
  error?: string;
}

interface MCPServerCardProps {
  server: MCPServer;
  onRefresh: () => void;
  onEdit?: (server: MCPServer) => void;
  onDelete?: (serverId: string) => void;
}

export function MCPServerCard({ server, onRefresh, onEdit, onDelete }: MCPServerCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const getStatus = () => {
    if (server.status === 'connected') {
      return { status: 'connected' as const, label: t('connected') || 'Connected', icon: '✅' };
    } else if (server.status === 'error') {
      return { status: 'error' as const, label: t('error') || 'Error', icon: '❌' };
    } else {
      return { status: 'not_configured' as const, label: t('disconnected') || 'Disconnected', icon: '⚪' };
    }
  };

  const status = getStatus();

  const handleDelete = async () => {
    if (!onDelete) return;
    setDeleting(true);
    try {
      await onDelete(server.id);
      setShowDeleteConfirm(false);
    } catch (err) {
      console.error('Failed to delete server:', err);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card hover className="flex flex-col h-full">
      <div className="flex items-start mb-4 flex-shrink-0">
        <div className="flex items-start space-x-3 flex-1 min-w-0">
          <span className="text-2xl flex-shrink-0">🔌</span>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1.5 leading-tight">{server.name}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
              {server.transport === 'stdio' ? 'STDIO' : 'HTTP/SSE'}
            </p>
            {server.tools_count !== undefined && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {server.tools_count} {t('tools') || 'tools'}
              </p>
            )}
            {server.error && (
              <p className="text-xs text-red-500 dark:text-red-400 mt-1">{server.error}</p>
            )}
          </div>
        </div>
      </div>

      {showDeleteConfirm ? (
        <div className="mt-auto pt-4 border-t border-gray-200 dark:border-gray-700 flex-shrink-0">
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">{t('confirmDelete') || 'Are you sure you want to delete this server?'}</p>
          <div className="flex space-x-2">
            <button
              onClick={() => setShowDeleteConfirm(false)}
              className="flex-1 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
            >
              {t('cancel') || 'Cancel'}
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex-1 px-3 py-1.5 text-sm bg-red-600 dark:bg-red-700 text-white rounded-md hover:bg-red-700 dark:hover:bg-red-600 disabled:opacity-50"
            >
              {deleting ? (t('deleting') || 'Deleting...') : (t('delete') || 'Delete')}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between mt-auto pt-4 border-t border-gray-200 dark:border-gray-700 flex-shrink-0">
          <StatusPill
            status={status.status}
            label={status.label}
            icon={status.icon}
          />
          <div className="flex space-x-2">
            {onEdit && (
              <button
                onClick={() => onEdit(server)}
                className="text-sm px-3 py-1 text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 whitespace-nowrap"
              >
                {t('edit') || 'Edit'}
              </button>
            )}
            <button
              onClick={onRefresh}
              className="text-sm px-3 py-1 text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 whitespace-nowrap"
            >
              {t('refresh') || 'Refresh'}
            </button>
            {onDelete && (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="text-sm px-3 py-1 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 whitespace-nowrap"
              >
                {t('delete') || 'Delete'}
              </button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

