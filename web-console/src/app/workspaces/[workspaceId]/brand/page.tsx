'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import ProjectsPanel from '../components/ProjectsPanel';
// Cloud capabilities import removed

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function BrandWorkspacePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const { workspace, isLoadingWorkspace } = useWorkspaceData();

  if (isLoadingWorkspace) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-secondary">Loading workspace...</div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-500">Workspace not found</div>
      </div>
    );
  }

  if (workspace.workspace_type !== 'brand') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-secondary">This is not a brand workspace</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b dark:border-gray-700 bg-surface-accent dark:bg-gray-900">
        <h1 className="text-2xl font-bold text-primary dark:text-gray-100">
          {workspace.title}
        </h1>
        {workspace.description && (
          <p className="text-sm text-secondary dark:text-gray-400 mt-1">
            {workspace.description}
          </p>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* Brand Foundation Cards */}
          <section>
            <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
              Brand Foundation
            </h2>
            <BrandFoundationCards workspaceId={workspaceId} />
          </section>

          {/* Projects List */}
          <section>
            <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
              Projects
            </h2>
            <div className="border rounded-lg overflow-hidden bg-surface-accent dark:bg-gray-800">
              <ProjectsPanel
                workspaceId={workspaceId}
                apiUrl={API_URL}
              />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
