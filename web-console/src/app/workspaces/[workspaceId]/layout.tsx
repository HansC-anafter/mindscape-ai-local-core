'use client';

import React from 'react';
import { WorkspaceDataProvider } from '@/contexts/WorkspaceDataContext';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
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
  const { workspaceId } = params;

  return (
    <WorkspaceDataProvider workspaceId={workspaceId}>
      <ExecutionContextProvider workspaceId={workspaceId}>
        <div className="flex flex-col h-screen">
          <Header />
          <div className="flex flex-1 overflow-hidden">
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </div>
        </div>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}

