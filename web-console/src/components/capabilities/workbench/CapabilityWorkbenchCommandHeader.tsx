'use client';

import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

import type { CapabilityWorkbenchCommandHeaderProps } from '@/types/capability-workbench';
import { useCapabilityWorkbenchPlacement } from './CapabilityWorkbenchResponsiveFrame';
import {
  useCapabilityWorkbenchMobileFloatingControlsRegistration,
  useOptionalCapabilityWorkbenchMobileFloatingControls,
  type CapabilityWorkbenchMobileFloatingControl,
} from './useCapabilityWorkbenchMobileFloatingControls';

function SlotFrame({
  children,
  className = '',
  testId,
}: {
  children: React.ReactNode;
  className?: string;
  testId: string;
}) {
  if (!children) {
    return null;
  }
  return (
    <div className={`min-w-0 ${className}`} data-testid={testId}>
      {children}
    </div>
  );
}

export function CapabilityWorkbenchCommandHeader({
  brandSlot,
  modeSlot,
  primaryToolbarSlot,
  contextToolbarSlot,
  statusSlot,
  utilitySlot,
  mobileVariant = 'default',
  mobileCollapsible,
  mobileDefaultCollapsed = false,
  className = '',
}: CapabilityWorkbenchCommandHeaderProps) {
  const placement = useCapabilityWorkbenchPlacement();
  const mobileFloatingControls = useOptionalCapabilityWorkbenchMobileFloatingControls();
  const useCompactMobileLayout = mobileVariant === 'compact' && placement === 'mobile';
  const compactMobileCollapsible = useCompactMobileLayout && (mobileCollapsible ?? true);
  const [compactMobileCollapsed, setCompactMobileCollapsed] = React.useState(mobileDefaultCollapsed);
  const externalizeUtilitySlot = useCompactMobileLayout && Boolean(utilitySlot) && Boolean(mobileFloatingControls);
  const mobileUtilityControlScopeId = React.useId();
  const mobileUtilityControls = React.useMemo<CapabilityWorkbenchMobileFloatingControl[]>(() => {
    if (!externalizeUtilitySlot || !utilitySlot) {
      return [];
    }
    return [{
      key: 'capability-header-utility',
      order: 30,
      render: () => (
        <div data-testid="capability-workbench-command-header-floating-utility">
          {utilitySlot}
        </div>
      ),
    }];
  }, [externalizeUtilitySlot, utilitySlot]);

  useCapabilityWorkbenchMobileFloatingControlsRegistration(
    mobileUtilityControlScopeId,
    mobileUtilityControls,
  );

  React.useEffect(() => {
    setCompactMobileCollapsed(compactMobileCollapsible ? mobileDefaultCollapsed : false);
  }, [compactMobileCollapsible, mobileDefaultCollapsed]);

  if (useCompactMobileLayout) {
    const showCompactMobileDetails = !compactMobileCollapsible || !compactMobileCollapsed;
    const compactMetaSlots = [
      {
        children: primaryToolbarSlot,
        className: 'shrink-0',
        testId: 'capability-workbench-command-header-primary-toolbar',
      },
      {
        children: contextToolbarSlot,
        className: 'shrink-0',
        testId: 'capability-workbench-command-header-context-toolbar',
      },
      {
        children: statusSlot,
        className: 'shrink-0',
        testId: 'capability-workbench-command-header-status',
      },
    ].filter((slot) => Boolean(slot.children));

    return (
      <header
        className={`grid shrink-0 grid-cols-1 gap-2 border-b border-stone-800 bg-stone-950 px-3 py-2 text-stone-100 ${className}`.trim()}
        data-testid="capability-workbench-command-header"
        data-mobile-variant="compact"
        data-mobile-collapsible={compactMobileCollapsible ? 'true' : 'false'}
        data-mobile-collapsed={compactMobileCollapsed ? 'true' : 'false'}
      >
        <div className="flex min-w-0 items-start gap-2">
          <SlotFrame
            className="min-w-0 flex-1"
            testId="capability-workbench-command-header-brand"
          >
            {brandSlot}
          </SlotFrame>
          {compactMobileCollapsible ? (
            <button
              type="button"
              aria-label={compactMobileCollapsed ? 'Expand workbench header' : 'Collapse workbench header'}
              aria-expanded={!compactMobileCollapsed}
              onClick={() => setCompactMobileCollapsed((current) => !current)}
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-stone-700 bg-stone-900/80 text-stone-200 transition hover:border-stone-500 hover:bg-stone-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="capability-workbench-command-header-mobile-collapse-toggle"
            >
              {compactMobileCollapsed ? (
                <ChevronDown aria-hidden className="h-4 w-4" />
              ) : (
                <ChevronUp aria-hidden className="h-4 w-4" />
              )}
            </button>
          ) : null}
          <SlotFrame
            className="shrink-0"
            testId="capability-workbench-command-header-utility"
          >
            {externalizeUtilitySlot ? null : utilitySlot}
          </SlotFrame>
        </div>
        {showCompactMobileDetails ? (
          <>
            <SlotFrame
              className="min-w-0 max-w-full"
              testId="capability-workbench-command-header-mode"
            >
              {modeSlot}
            </SlotFrame>
            {compactMetaSlots.length > 0 ? (
              <div
                className="flex min-w-0 items-center gap-2 overflow-x-auto pb-0.5"
                data-testid="capability-workbench-command-header-mobile-meta-strip"
              >
                {compactMetaSlots.map((slot) => (
                  <SlotFrame
                    key={slot.testId}
                    className={slot.className}
                    testId={slot.testId}
                  >
                    {slot.children}
                  </SlotFrame>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div
            aria-hidden="true"
            className="hidden"
            data-testid="capability-workbench-command-header-collapsed-content"
          >
            {modeSlot}
            {primaryToolbarSlot}
            {contextToolbarSlot}
            {statusSlot}
          </div>
        )}
      </header>
    );
  }

  return (
    <header
      className={`flex min-h-[56px] shrink-0 flex-wrap items-center gap-2 border-b border-stone-800 bg-stone-950 px-3 py-2 text-stone-100 md:flex-nowrap md:gap-3 ${className}`.trim()}
      data-testid="capability-workbench-command-header"
    >
      <SlotFrame
        className="w-full shrink-0 md:w-[220px]"
        testId="capability-workbench-command-header-brand"
      >
        {brandSlot}
      </SlotFrame>
      <SlotFrame
        className="max-w-full shrink-0 overflow-x-auto"
        testId="capability-workbench-command-header-mode"
      >
        {modeSlot}
      </SlotFrame>
      <SlotFrame
        className="max-w-full shrink-0 overflow-x-auto"
        testId="capability-workbench-command-header-primary-toolbar"
      >
        {primaryToolbarSlot}
      </SlotFrame>
      <SlotFrame
        className="min-w-[120px] flex-1 md:min-w-[160px]"
        testId="capability-workbench-command-header-context-toolbar"
      >
        {contextToolbarSlot}
      </SlotFrame>
      <SlotFrame
        className="max-w-full shrink-0 overflow-x-auto"
        testId="capability-workbench-command-header-status"
      >
        {statusSlot}
      </SlotFrame>
      <SlotFrame
        className="shrink-0"
        testId="capability-workbench-command-header-utility"
      >
        {utilitySlot}
      </SlotFrame>
    </header>
  );
}

export default CapabilityWorkbenchCommandHeader;
