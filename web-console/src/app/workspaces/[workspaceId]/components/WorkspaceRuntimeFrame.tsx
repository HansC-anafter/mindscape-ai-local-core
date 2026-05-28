'use client';

import React from 'react';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
import type { WorkspaceDataInitialLoadProfile } from '@/contexts/WorkspaceDataContext';
import WorkspaceGlobalToolRailProvider from './WorkspaceGlobalToolRailProvider';

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
        <WorkspaceGlobalToolRailProvider workspaceId={workspaceId}>
          {children}
        </WorkspaceGlobalToolRailProvider>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}
