'use client';

import React from 'react';
import Header from '@/components/Header';
import UpdateBanner from '@/components/sync/UpdateBanner';
import WorkspaceRuntimeFrame from './WorkspaceRuntimeFrame';

interface WorkspaceChromeProps {
  workspaceId: string;
  children: React.ReactNode;
}

export default function WorkspaceChrome({
  workspaceId,
  children,
}: WorkspaceChromeProps) {
  return (
    <>
      <Header />
      <UpdateBanner clientVersion="1.0.0" />
      <WorkspaceRuntimeFrame workspaceId={workspaceId}>
        {children}
      </WorkspaceRuntimeFrame>
    </>
  );
}
