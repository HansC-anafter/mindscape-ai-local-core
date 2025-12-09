'use client';

import React, { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import SandboxViewer from '@/components/sandbox/SandboxViewer';
import { getSandbox, Sandbox } from '@/lib/sandbox-api';

/**
 * Standalone Sandbox Page
 * 
 * Opens sandbox viewer in a dedicated page/window.
 * URL: /workspaces/[workspaceId]/sandbox/[sandboxId]
 * 
 * Benefits:
 * - Persists when switching playbooks
 * - Can be opened in new browser window
 * - Full screen available
 */
export default function SandboxPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const sandboxId = params.sandboxId as string;
  
  const [sandbox, setSandbox] = useState<Sandbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSandbox = async () => {
      try {
        setLoading(true);
        const data = await getSandbox(workspaceId, sandboxId);
        setSandbox(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load sandbox');
      } finally {
        setLoading(false);
      }
    };

    if (workspaceId && sandboxId) {
      loadSandbox();
    }
  }, [workspaceId, sandboxId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading sandbox...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-500 text-6xl mb-4">⚠️</div>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2">
            Failed to Load Sandbox
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => window.close()}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              title="Close window"
            >
              ✕
            </button>
            <div>
              <h1 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
                Sandbox: {sandbox?.sandbox_type || 'Unknown'}
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {sandboxId}
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => window.location.reload()}
              className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              title="Refresh"
            >
              🔄 Refresh
            </button>
          </div>
        </div>
      </header>

      {/* Sandbox Viewer */}
      <main className="h-[calc(100vh-60px)]">
        <SandboxViewer
          workspaceId={workspaceId}
          sandboxId={sandboxId}
        />
      </main>
    </div>
  );
}

