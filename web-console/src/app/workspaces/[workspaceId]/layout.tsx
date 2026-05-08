'use client';

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';

interface WorkspaceLayoutProps {
  children: React.ReactNode;
  params: { workspaceId: string };
}

type WorkspaceChromeComponent = React.ComponentType<{
  workspaceId: string;
  children: React.ReactNode;
}>;

/**
 * WorkspaceLayout - Root layout for workspace pages
 *
 * Provides dynamic left sidebar (dispatch center) and fixed right sidebar.
 * Left sidebar changes based on active playbook, right sidebar remains fixed.
 * For brand workspaces, shows brand-specific navigation.
 */
export default function WorkspaceLayout({
  children,
  params
}: WorkspaceLayoutProps) {
  const { workspaceId } = params;
  const pathname = usePathname();
  const isCapabilityEntryPath = Boolean(
    pathname?.match(/^\/workspaces\/[^/]+\/capabilities\/[^/]+$/)
  );
  const isPerformanceDirectionCapabilityPath = Boolean(
    pathname?.match(/^\/workspaces\/[^/]+\/capabilities\/performance_direction(?:\/.*)?$/)
  );
  const isPerformanceDirectionStaticHostPath = Boolean(
    pathname?.match(/^\/workspaces\/[^/]+\/capability-ui-hosts\/performance_direction(?:\/.*)?$/)
  );
  const shouldBypassWorkspaceChrome =
    isCapabilityEntryPath ||
    isPerformanceDirectionCapabilityPath ||
    isPerformanceDirectionStaticHostPath;
  const [WorkspaceChrome, setWorkspaceChrome] = useState<WorkspaceChromeComponent | null>(null);

  useEffect(() => {
    if (shouldBypassWorkspaceChrome) {
      setWorkspaceChrome(null);
      return;
    }

    let cancelled = false;
    void import('./components/WorkspaceChrome')
      .then((module) => {
        if (!cancelled) {
          setWorkspaceChrome(() => module.default);
        }
      })
      .catch((error) => {
        console.error('[WorkspaceLayout] Failed to load workspace chrome:', error);
      });

    return () => {
      cancelled = true;
    };
  }, [shouldBypassWorkspaceChrome]);

  if (shouldBypassWorkspaceChrome) {
    return (
      <div className="flex h-screen flex-col">
        <div className="relative flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-hidden">
            {children}
          </main>
        </div>
      </div>
    );
  }

  if (!WorkspaceChrome) {
    return (
      <div className="flex h-screen flex-col">
        <div className="relative flex flex-1 overflow-hidden" />
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <WorkspaceChrome workspaceId={workspaceId}>
        {children}
      </WorkspaceChrome>
    </div>
  );
}
