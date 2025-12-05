'use client';

import React, { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function ExecutionPageContent({ workspaceId, executionId }: { workspaceId: string; executionId: string }) {
  const router = useRouter();

  useEffect(() => {
    // Redirect to workspace page with execution focus
    // The workspace page will handle showing the execution inspector
    const workspaceUrl = `/workspaces/${workspaceId}`;

    // Dispatch event to open execution inspector
    window.dispatchEvent(new CustomEvent('open-execution-inspector', {
      detail: { executionId }
    }));

    // Update URL to workspace page (execution will be shown via state)
    router.replace(workspaceUrl);
  }, [workspaceId, executionId, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <p className="text-gray-600 dark:text-gray-400">Loading execution...</p>
      </div>
    </div>
  );
}

export default function ExecutionPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const executionId = params.executionId as string;

  if (!workspaceId || !executionId) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400">Invalid workspace or execution ID</p>
        </div>
      </div>
    );
  }

  return (
    <WorkspaceDataProvider workspaceId={workspaceId}>
      <ExecutionPageContent workspaceId={workspaceId} executionId={executionId} />
    </WorkspaceDataProvider>
  );
}

