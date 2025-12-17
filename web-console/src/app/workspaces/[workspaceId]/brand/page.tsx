'use client';

import React from 'react';
import { useParams } from 'next/navigation';
import { useWorkspaceData } from '@/contexts/WorkspaceDataContext';
import ProjectsPanel from '../components/ProjectsPanel';
import BrandFoundationCards from '/mindscape-ai-cloud/capabilities/brand_identity/ui/BrandFoundationCards';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function BrandWorkspacePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const { workspace, isLoadingWorkspace } = useWorkspaceData();

  if (isLoadingWorkspace) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">Loading workspace...</div>
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
        <div className="text-gray-500">This is not a brand workspace</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b dark:border-gray-700 bg-white dark:bg-gray-900">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {workspace.title}
        </h1>
        {workspace.description && (
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {workspace.description}
          </p>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* Brand Foundation Cards */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Brand Foundation
            </h2>
            <BrandFoundationCards workspaceId={workspaceId} />
          </section>

          {/* Projects List */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Projects
            </h2>
            <div className="border rounded-lg overflow-hidden bg-white dark:bg-gray-800">
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
