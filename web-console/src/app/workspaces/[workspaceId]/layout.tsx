'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
import { DynamicLeftSidebar } from '@/components/playbooks/DynamicLeftSidebar';
import { usePlaybookLeftSidebar } from '@/hooks/usePlaybookLeftSidebar';
import Header from '../../../components/Header';

interface WorkspaceLayoutProps {
  children: React.ReactNode;
  params: { workspaceId: string };
}

/**
 * WorkspaceLayout - Root layout for workspace pages
 *
 * Provides dynamic left sidebar (dispatch center) and fixed right sidebar.
 * Left sidebar changes based on active playbook, right sidebar remains fixed.
 */
export default function WorkspaceLayout({
  children,
  params
}: WorkspaceLayoutProps) {
  const pathname = usePathname();
  const { workspaceId } = params;

  const isPlaybookSurface = pathname?.includes('/playbook/');
  const playbookCode = isPlaybookSurface
    ? pathname?.split('/playbook/')[1]?.split('/')[0] || null
    : null;

  const { config: leftSidebarConfig } = usePlaybookLeftSidebar(playbookCode);

  return (
    <WorkspaceDataProvider workspaceId={workspaceId}>
      <ExecutionContextProvider workspaceId={workspaceId}>
        <div className="flex flex-col h-screen">
          <Header />
          <div className="flex flex-1 overflow-hidden">
            <DynamicLeftSidebar
              playbookCode={playbookCode}
              workspaceId={workspaceId}
              config={leftSidebarConfig}
            />
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </div>
        </div>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}

