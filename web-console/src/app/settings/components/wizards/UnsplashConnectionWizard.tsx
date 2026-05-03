'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';
import { useWorkspaceDataOptional } from '../../../../contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '../../../../lib/api-url';

interface UnsplashConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

interface Workspace {
  id: string;
  title: string;
  description?: string;
  unsplashConfigured?: boolean;
  unsplashStatus?: string;
}

export function UnsplashConnectionWizard({
  onClose,
  onSuccess,
}: UnsplashConnectionWizardProps) {
  const params = useParams();
  const workspaceData = useWorkspaceDataOptional();

  // Try to get workspace ID from multiple sources
  const urlWorkspaceId = params?.workspaceId as string | undefined;
  const contextWorkspaceId = workspaceData?.workspace?.id;
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // Final workspace ID: selected > context > URL params
  const workspaceId = selectedWorkspaceId || contextWorkspaceId || urlWorkspaceId;

  const [form, setForm] = useState({
    application_id: '',
    access_key: '',
    secret_key: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [currentConfig, setCurrentConfig] = useState<{
    configured: boolean;
    status?: string;
    configured_at?: string;
    application_id?: string;
  } | null>(null);

  const loadWorkspaces = useCallback(async () => {
    setLoadingWorkspaces(true);
    try {
      const apiUrl = getApiBaseUrl();
      const ownerUserId = 'default-user';
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces?owner_user_id=${ownerUserId}&limit=50`,
        {
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );
      if (response.ok) {
        const data = await response.json();
        const workspaceList = Array.isArray(data) ? data : [];

        // Load Unsplash config status for each workspace
        const workspacesWithConfig = await Promise.all(
          workspaceList.map(async (ws: Workspace) => {
            try {
              const configResponse = await fetch(
                `${apiUrl}/api/v1/workspaces/${ws.id}/web-generation/unsplash/config`
              );
              if (configResponse.ok) {
                const config = await configResponse.json();
                return {
                  ...ws,
                  unsplashConfigured: config.configured || false,
                  unsplashStatus: config.status || undefined,
                };
              }
            } catch (err) {
              console.error(`Failed to load config for workspace ${ws.id}:`, err);
            }
            return {
              ...ws,
              unsplashConfigured: false,
            };
          })
        );

        setWorkspaces(workspacesWithConfig);

        // Auto-select workspace if only one available
        if (workspacesWithConfig.length === 1 && !workspaceId) {
          setSelectedWorkspaceId(workspacesWithConfig[0].id);
        } else if (workspaceId) {
          setSelectedWorkspaceId(workspaceId);
        }
      } else {
        console.error('Failed to load workspaces:', response.status, response.statusText);
      }
    } catch (err) {
      console.error('Failed to load workspaces:', err);
    } finally {
      setLoadingWorkspaces(false);
    }
  }, [workspaceId]);

  const loadCurrentConfig = useCallback(async () => {
    if (!workspaceId) return;

    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`
      );
      if (response.ok) {
        const config = await response.json();
        setCurrentConfig(config);
      }
    } catch (err) {
      console.error('Failed to load Unsplash config:', err);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  useEffect(() => {
    if (workspaceId) {
      loadCurrentConfig();
    }
  }, [workspaceId, loadCurrentConfig]);

  const handleSave = async () => {
    if (!workspaceId) {
      setError('Workspace ID is required');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            application_id: form.application_id,
            access_key: form.access_key,
            secret_key: form.secret_key || undefined,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save Unsplash configuration');
      }

      setSuccess('Unsplash API key configured successfully');
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Configuration failed';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!workspaceId) {
      setError('Workspace ID is required');
      return;
    }

    if (!confirm('Delete the Unsplash configuration?')) {
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`,
        {
          method: 'DELETE',
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete Unsplash configuration');
      }

      setSuccess('Unsplash configuration deleted');
      setCurrentConfig({ configured: false });
      setForm({ application_id: '', access_key: '', secret_key: '' });
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Delete failed';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const footer = (
    <>
      {currentConfig?.configured && (
        <button
          onClick={handleDelete}
          disabled={loading}
          className="px-4 py-2 text-red-600 dark:text-red-400 border border-red-300 dark:border-red-600 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Delete configuration
        </button>
      )}
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel' as any)}
      </button>
      <button
        onClick={handleSave}
        disabled={loading || !workspaceId || !form.application_id.trim() || !form.access_key.trim()}
        className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? 'Saving...' : currentConfig?.configured ? 'Update configuration' : 'Save configuration'}
      </button>
    </>
  );

  return (
    <WizardShell
      title="Configure Unsplash"
      onClose={onClose}
      error={error}
      success={success}
      footer={footer}
    >
      <div className="space-y-6">
        <div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Unsplash provides high-quality photography. Configure an API key to use Unsplash images for Visual Lens generation.
          </p>

          {/* Workspace Selector */}
          {workspaces.length > 1 && (
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Select workspace <span className="text-red-500">*</span>
              </label>
              <select
                value={selectedWorkspaceId}
                onChange={(e) => setSelectedWorkspaceId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
                disabled={loadingWorkspaces}
              >
                <option value="">Select a workspace</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>
                    {ws.title} {ws.description ? `(${ws.description})` : ''}
                    {ws.unsplashConfigured ? ` - Configured${ws.unsplashStatus ? ` [${ws.unsplashStatus}]` : ''}` : ''}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Each workspace can have its own Unsplash API key.
              </p>
            </div>
          )}

          {workspaceId && workspaces.length === 1 && (
            <div className="mb-4 p-2 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded">
              <p className="text-xs text-accent dark:text-blue-300">
                Workspace: {workspaces.find(w => w.id === workspaceId)?.title || workspaceId}
              </p>
            </div>
          )}

          {!workspaceId && workspaces.length === 0 && !loadingWorkspaces && (
            <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded">
              <p className="text-sm text-yellow-700 dark:text-yellow-300">
                Unable to load the workspace list. Make sure you are signed in and have access to the workspace.
              </p>
            </div>
          )}

          {currentConfig?.configured && (
            <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded">
              <p className="text-sm text-green-700 dark:text-green-300">
                Configured (status: {currentConfig.status || 'active'})
                {currentConfig.configured_at && (
                  <span className="text-xs ml-2">
                    Configured at: {new Date(currentConfig.configured_at).toLocaleString()}
                  </span>
                )}
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Application ID <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={form.application_id}
            onChange={(e) => setForm({ ...form, application_id: e.target.value })}
            placeholder="Enter your Unsplash Application ID"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Access Key (Client-ID) <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            value={form.access_key}
            onChange={(e) => setForm({ ...form, access_key: e.target.value })}
            placeholder="Enter your Unsplash Access Key"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Secret Key <span className="text-gray-400 text-xs">(optional, used for OAuth)</span>
          </label>
          <input
            type="password"
            value={form.secret_key}
            onChange={(e) => setForm({ ...form, secret_key: e.target.value })}
            placeholder="Enter your Unsplash Secret Key (optional)"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div className="mt-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            You can create and retrieve these credentials from{' '}
            <a
              href="https://unsplash.com/developers"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent dark:text-blue-400 hover:underline"
            >
              Unsplash Developers
            </a>{' '}
          </p>
        </div>

        <div className="p-4 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded">
          <h4 className="text-sm font-medium text-accent dark:text-blue-300 mb-2">
            Important notes
          </h4>
          <ul className="text-xs text-accent dark:text-blue-200 space-y-1 list-disc list-inside">
            <li>API keys are stored in workspace settings.</li>
            <li>Using Unsplash images must comply with the Unsplash terms.</li>
            <li>Image downloads must be reported; the system handles this automatically.</li>
            <li>Photographer attribution must be shown; the system handles this automatically.</li>
          </ul>
        </div>
      </div>
    </WizardShell>
  );
}
