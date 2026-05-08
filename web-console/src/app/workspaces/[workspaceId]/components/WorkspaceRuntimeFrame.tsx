'use client';

import React from 'react';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
import { AOLRuntimeShellProvider } from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import BrandNavigation from '@/components/brand/BrandNavigation';

interface WorkspaceRuntimeFrameProps {
  workspaceId: string;
  children: React.ReactNode;
}

export default function WorkspaceRuntimeFrame({
  workspaceId,
  children,
}: WorkspaceRuntimeFrameProps) {
  return (
    <WorkspaceDataProvider workspaceId={workspaceId}>
      <ExecutionContextProvider workspaceId={workspaceId}>
        <AOLRuntimeShellProvider workspaceId={workspaceId}>
          <div className="relative flex flex-1 overflow-hidden">
            <BrandNavigation workspaceId={workspaceId} />
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </div>
        </AOLRuntimeShellProvider>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}
