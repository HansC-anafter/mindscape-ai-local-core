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
  aolHost?: AddressableObjectHostBridge;
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
  const navigationState = showNavigation ? 'open' : 'closed';

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

  const collapseNavigation = React.useCallback(() => {
    if (!showNavigation) {
      return;
    }
    setNavigationCollapsed(true);
    setNavigationHoverOpen(false);
  }, [showNavigation]);

  React.useEffect(() => {
    if (!showNavigation || typeof document === 'undefined') {
      return undefined;
    }

    function handleDocumentInteraction() {
      removeDocumentInteractionListeners();
      collapseNavigation();
    }

    function removeDocumentInteractionListeners() {
      document.removeEventListener('click', handleDocumentInteraction, true);
      document.removeEventListener('scroll', handleDocumentInteraction, true);
      window.removeEventListener('scroll', handleDocumentInteraction, true);
    }

    document.addEventListener('click', handleDocumentInteraction, true);
    document.addEventListener('scroll', handleDocumentInteraction, { capture: true, passive: true });
    window.addEventListener('scroll', handleDocumentInteraction, { capture: true, passive: true });
    return removeDocumentInteractionListeners;
  }, [collapseNavigation, showNavigation]);

  return (
    <div
      className={className || 'relative flex min-h-0 flex-1 overflow-hidden'}
      data-testid="capability-workbench-shell"
      data-capability-code={capabilityCode}
    >
      <div
        className="flex min-h-0 shrink-0 overflow-hidden"
        data-testid="capability-workbench-navigation-region"
        data-navigation-state={navigationState}
        onMouseLeave={handleNavigationRegionMouseLeave}
      >
        <div
          aria-hidden={!showNavigation}
          className={`min-h-0 shrink-0 overflow-hidden transition-[width,opacity] duration-200 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
            showNavigation ? 'w-64 opacity-100' : 'w-0 opacity-0'
          }`}
          data-testid="capability-workbench-navigation-slot"
          data-navigation-state={navigationState}
        >
          {navigation}
        </div>
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
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden" data-testid="capability-workbench-content-slot">
        {children}
      </div>
    </div>
  );
}

export default CapabilityWorkbenchShell;
