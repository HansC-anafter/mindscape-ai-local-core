'use client';

/**
 * Web Generation Page
 *
 * Main page for web generation module with baseline management.
 */

import React from 'react';
import { useParams, useRouter } from 'next/navigation';
import { WebGenerationContextBar } from './components/WebGenerationContextBar';
import VisualLensPreview from '@/components/web-generation/VisualLensPreview';

export default function WebGenerationPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();

  // Extract projectId from query params if needed
  // For now, we'll use workspace-level baseline
  const projectId = undefined; // TODO: Extract from query params when needed

  const handleImport = () => {
    // Navigate to import/snapshot ingestion page
    router.push(`/workspaces/${workspaceId}/web-generation/import`);
  };

  const handleDiff = () => {
    // Navigate to diff view
    router.push(`/workspaces/${workspaceId}/web-generation/diff`);
  };

  const handleReview = () => {
    // Navigate to review/changes view
    router.push(`/workspaces/${workspaceId}/web-generation/review`);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Context Bar */}
      <WebGenerationContextBar
        workspaceId={workspaceId}
        projectId={projectId}
        onImport={handleImport}
        onDiff={handleDiff}
        onReview={handleReview}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-primary dark:text-gray-100 mb-2">
              Web Generation
            </h1>
            <p className="text-secondary dark:text-gray-400">
              Manage design snapshots, baselines, and generate web projects
            </p>
          </div>

          {/* Placeholder Content */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Design Snapshots */}
            <div className="bg-surface-secondary dark:bg-gray-900 border border-default dark:border-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
                Design Snapshots
              </h2>
              <p className="text-secondary dark:text-gray-400 mb-4">
                Manage design snapshots from external tools (Stitch, Figma, etc.)
              </p>
              <button
                onClick={handleImport}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Import Snapshot
              </button>
            </div>

            {/* Baseline Management */}
            <div className="bg-surface-secondary dark:bg-gray-900 border border-default dark:border-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
                Baseline Management
              </h2>
              <p className="text-secondary dark:text-gray-400 mb-4">
                Set and manage design baselines for your projects
              </p>
              <p className="text-sm text-secondary dark:text-gray-500">
                Use the context bar above to set or manage your baseline.
              </p>
            </div>

            {/* Version History */}
            <div className="bg-surface-secondary dark:bg-gray-900 border border-default dark:border-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
                Version History
              </h2>
              <p className="text-secondary dark:text-gray-400 mb-4">
                View and compare different versions of your design snapshots
              </p>
              <button
                onClick={handleDiff}
                className="px-4 py-2 border border-default dark:border-gray-600 text-primary dark:text-gray-300 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
              >
                View Diff
              </button>
            </div>

            {/* Playbooks */}
            <div className="bg-surface-secondary dark:bg-gray-900 border border-default dark:border-gray-800 rounded-lg p-6">
              <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
                Generation Playbooks
              </h2>
              <p className="text-secondary dark:text-gray-400 mb-4">
                Run playbooks to generate web projects from your design snapshots
              </p>
              <p className="text-sm text-secondary dark:text-gray-500">
                Use playbooks like <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">page_outline</code>,{' '}
                <code className="px-1 py-0.5 bg-surface-secondary dark:bg-gray-800 rounded">site_spec_generation</code>, and{' '}
                <code className="px-1 py-0.5 bg-surface-secondary dark:bg-gray-800 rounded">style_system_gen</code>
              </p>
            </div>

            {/* Visual Lens Preview */}
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-6 md:col-span-2">
              <h2 className="text-xl font-semibold text-primary dark:text-gray-100 mb-4">
                Visual Lens
              </h2>
              <VisualLensPreview
                workspaceId={workspaceId}
                projectId={projectId}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
