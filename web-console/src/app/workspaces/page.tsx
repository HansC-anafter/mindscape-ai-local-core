'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import Header from '../../components/Header';
import ConfirmDialog from '../../components/ConfirmDialog';
import { t } from '@/lib/i18n';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Workspace {
  id: string;
  title: string;
  description?: string;
  primary_project_id?: string;
  created_at: string;
  updated_at: string;
  launch_status?: string;
  starter_kit_type?: string;
}

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ownerUserId] = useState('default-user'); // TODO: Get from auth context
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const router = useRouter();
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const loadingRef = useRef(false);

  const loadWorkspaces = useCallback(async () => {
    if (!isMountedRef.current) return;
    if (loadingRef.current) return;

    loadingRef.current = true;

    try {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      const response = await fetch(
        `${API_URL}/api/v1/workspaces?owner_user_id=${ownerUserId}&limit=50`,
        {
          signal: abortControllerRef.current.signal,
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );

      if (!isMountedRef.current) {
        loadingRef.current = false;
        return;
      }

      if (response.ok) {
        try {
          const data = await response.json();

          if (isMountedRef.current) {
            setWorkspaces(Array.isArray(data) ? data : []);
            setError(null);
            setLoading(false);
          }
        } catch (jsonErr) {
          console.error('[loadWorkspaces] JSON parse error:', jsonErr);
          if (isMountedRef.current) {
            setError('Failed to parse workspace data');
            setLoading(false);
          }
        }
      } else {
        let errorMessage = 'Failed to load workspaces';
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorMessage = `Failed to load workspaces: ${typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail)}`;
          }
        } catch (parseErr) {
          errorMessage = `Failed to load workspaces: ${response.status} ${response.statusText}`;
        }
        console.error('[loadWorkspaces] Error response:', errorMessage);
        if (isMountedRef.current) {
          setError(errorMessage);
          setLoading(false);
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        loadingRef.current = false;
        return;
      }
      if (isMountedRef.current) {
        setError(`Failed to load workspaces: ${err instanceof Error ? err.message : String(err)}`);
        setLoading(false);
      }
      loadingRef.current = false;
    }
  }, [ownerUserId]);

  useEffect(() => {
    isMountedRef.current = true;
    loadWorkspaces();

    return () => {
      isMountedRef.current = false;
      loadingRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [loadWorkspaces]);

  const handleCreateWorkspace = async (title: string, description: string) => {
    try {
      const response = await fetch(
        `${API_URL}/api/v1/workspaces?owner_user_id=${ownerUserId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            title: title,
            description: description || ''
          })
        }
      );

      if (response.ok) {
        const newWorkspace = await response.json();
        setWorkspaces(prev => [newWorkspace, ...prev]);
        setShowCreateModal(false);
      } else {
        let errorMessage = t('workspaceCreateFailed');
        try {
          const errorData = await response.json();
          // Try to extract error message from various possible fields
          if (errorData.detail) {
            errorMessage = `${t('workspaceCreateFailed')}: ${errorData.detail}`;
          } else if (errorData.message) {
            errorMessage = `${t('workspaceCreateFailed')}: ${errorData.message}`;
          } else if (errorData.error) {
            errorMessage = `${t('workspaceCreateFailed')}: ${errorData.error}`;
          } else if (typeof errorData === 'string') {
            errorMessage = `${t('workspaceCreateFailed')}: ${errorData}`;
          } else {
            errorMessage = `${t('workspaceCreateFailed')}: ${response.status} ${response.statusText}`;
          }
        } catch (parseError) {
          // If JSON parsing fails, use status text
          errorMessage = `${t('workspaceCreateFailed')}: ${response.status} ${response.statusText}`;
        }
        alert(errorMessage);
      }
    } catch (err) {
      const errorMessage = err instanceof Error
        ? `${t('workspaceCreateFailed')}: ${err.message}`
        : `${t('workspaceCreateFailed')}: ${String(err)}`;
      alert(errorMessage);
      console.error('Failed to create workspace:', err);
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!deleteTarget) return;

    setIsDeleting(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/workspaces/${deleteTarget.id}`, {
        method: 'DELETE',
      });

      if (response.ok || response.status === 204) {
        setWorkspaces(prev => prev.filter(w => w.id !== deleteTarget.id));
        setDeleteTarget(null);
      } else {
        let errorMessage = t('workspaceDeleteFailed');
        try {
          const errorData = await response.json();
          // Try to extract error message from various possible fields
          if (errorData.detail) {
            errorMessage = `${t('workspaceDeleteFailed')}: ${errorData.detail}`;
          } else if (errorData.message) {
            errorMessage = `${t('workspaceDeleteFailed')}: ${errorData.message}`;
          } else if (errorData.error) {
            errorMessage = `${t('workspaceDeleteFailed')}: ${errorData.error}`;
          } else if (typeof errorData === 'string') {
            errorMessage = `${t('workspaceDeleteFailed')}: ${errorData}`;
          } else {
            errorMessage = `${t('workspaceDeleteFailed')}: ${response.status} ${response.statusText}`;
          }
        } catch (parseError) {
          // If JSON parsing fails, use status text
          errorMessage = `${t('workspaceDeleteFailed')}: ${response.status} ${response.statusText}`;
        }
        alert(errorMessage);
      }
    } catch (err) {
      const errorMessage = err instanceof Error
        ? `${t('workspaceDeleteFailed')}: ${err.message}`
        : `${t('workspaceDeleteFailed')}: ${String(err)}`;
      alert(errorMessage);
      console.error('Failed to delete workspace:', err);
    } finally {
      setIsDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <Header />
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-gray-500 dark:text-gray-400">Loading workspaces...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Header />

      <div className="max-w-6xl mx-auto p-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Workspaces</h1>
          <button
            onClick={() => router.push('/workspaces/new/home')}
            className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
          >
            + New Workspace
          </button>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-red-700 dark:text-red-300">{error}</p>
            <button
              onClick={() => {
                setError(null);
                setLoading(true);
                loadWorkspaces();
              }}
              className="mt-2 px-4 py-2 bg-red-600 dark:bg-red-700 text-white rounded-lg hover:bg-red-700 dark:hover:bg-red-600 transition-colors"
            >
              {t('retryButton') || '重試'}
            </button>
          </div>
        )}

        {workspaces.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500 dark:text-gray-400 mb-4">No workspaces yet.</p>
            <button
              onClick={() => router.push('/workspaces/new/home')}
              className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600"
            >
              Create Your First Workspace
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces.map((workspace) => {
              const launchStatus = workspace.launch_status || 'pending';
              const statusConfig = {
                pending: { color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Pending' },
                ready: { color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', label: 'Ready' },
                active: { color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', label: 'Active' }
              };
              const status = statusConfig[launchStatus as keyof typeof statusConfig] || statusConfig.pending;

              return (
                <div
                  key={workspace.id}
                  className="group relative p-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-600 hover:shadow-md transition-all"
                >
                  <Link
                    href={
                      workspace.launch_status === 'pending'
                        ? `/workspaces/${workspace.id}/home?setup=true`
                        : `/workspaces/${workspace.id}`
                    }
                    className="block"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex-1">
                        {workspace.title}
                      </h3>
                      <span className={`ml-2 px-2 py-1 rounded-full text-xs font-medium ${status.color}`}>
                        {status.label}
                      </span>
                    </div>
                    {workspace.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
                        {workspace.description}
                      </p>
                    )}
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span>Updated: {new Date(workspace.updated_at).toLocaleDateString()}</span>
                      {workspace.starter_kit_type && (
                        <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">
                          {workspace.starter_kit_type}
                        </span>
                      )}
                    </div>
                  </Link>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDeleteTarget(workspace);
                    }}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-opacity"
                    title={t('workspaceDelete')}
                  >
                    🗑️
                  </button>
                </div>
              );
            })}
          </div>
        )}


        <ConfirmDialog
          isOpen={!!deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDeleteWorkspace}
          title={t('workspaceDelete')}
          message={deleteTarget ? t('workspaceDeleteConfirm', { workspaceName: deleteTarget.title }) : ''}
          confirmText={t('delete') || '刪除'}
          cancelText={t('cancel') || '取消'}
          confirmButtonClassName="bg-red-600 hover:bg-red-700"
        />
      </div>
    </div>
  );
}
