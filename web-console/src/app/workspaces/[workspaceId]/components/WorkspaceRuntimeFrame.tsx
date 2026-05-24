'use client';

import React from 'react';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
import type { WorkspaceDataInitialLoadProfile } from '@/contexts/WorkspaceDataContext';

interface WorkspaceRuntimeFrameProps {
  workspaceId: string;
  initialLoadProfile?: WorkspaceDataInitialLoadProfile;
  children: React.ReactNode;
}

export default function WorkspaceRuntimeFrame({
  workspaceId,
  initialLoadProfile,
  children,
}: WorkspaceRuntimeFrameProps) {
  return (
    <WorkspaceDataProvider workspaceId={workspaceId} initialLoadProfile={initialLoadProfile}>
      <ExecutionContextProvider workspaceId={workspaceId}>
        <div className="relative flex h-full min-h-0 flex-1 overflow-hidden">
          <main className="flex h-full min-h-0 flex-1 overflow-hidden">
            {children}
          </main>
        </div>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}
