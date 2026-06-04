'use client';

import React from 'react';

import type { AddressableObjectHostBridge } from '@/lib/addressable-object-layer';
import { PackScopeToolRailHost } from './PackScopeToolRailHost';
import { usePackScopeToolContributions } from './usePackScopeToolContributions';

interface CapabilityWorkbenchShellProps {
  workspaceId: string;
  capabilityCode: string;
  apiUrl: string;
  navigation?: React.ReactNode;
  children: React.ReactNode;
  aolHost?: Pick<AddressableObjectHostBridge, 'onSelectObject'>;
  className?: string;
}

export function CapabilityWorkbenchShell({
  workspaceId,
  capabilityCode,
  apiUrl,
  navigation = null,
  children,
  aolHost,
  className,
}: CapabilityWorkbenchShellProps) {
  const tools = usePackScopeToolContributions(capabilityCode);
  const [navigationCollapsed, setNavigationCollapsed] = React.useState(false);
  const [navigationHoverOpen, setNavigationHoverOpen] = React.useState(false);
  const showNavigation = !navigationCollapsed || navigationHoverOpen;

  const handleNavigationCollapsedChange = React.useCallback((collapsed: boolean) => {
    setNavigationCollapsed(collapsed);
    setNavigationHoverOpen(false);
  }, []);

  const handleNavigationToggleHover = React.useCallback(() => {
    if (navigationCollapsed) {
      setNavigationHoverOpen(true);
      return;
    }
    setNavigationCollapsed(true);
  }, [navigationCollapsed]);

  const handleNavigationRegionMouseLeave = React.useCallback(() => {
    if (navigationCollapsed) {
      setNavigationHoverOpen(false);
    }
  }, [navigationCollapsed]);

  return (
    <div
      className={className || 'relative flex min-h-0 flex-1 overflow-hidden'}
      data-testid="capability-workbench-shell"
      data-capability-code={capabilityCode}
    >
      <div
        className="flex min-h-0 shrink-0"
        data-testid="capability-workbench-navigation-region"
        onMouseLeave={handleNavigationRegionMouseLeave}
      >
        {showNavigation ? navigation : null}
        <PackScopeToolRailHost
          workspaceId={workspaceId}
          capabilityCode={capabilityCode}
          apiUrl={apiUrl}
          tools={tools}
          navigationCollapsed={!showNavigation}
          aolHost={aolHost}
          onNavigationCollapsedChange={handleNavigationCollapsedChange}
          onNavigationToggleHover={handleNavigationToggleHover}
        />
      </div>
      <div className="min-w-0 flex-1 overflow-hidden" data-testid="capability-workbench-content-slot">
        {children}
      </div>
    </div>
  );
}

export default CapabilityWorkbenchShell;
