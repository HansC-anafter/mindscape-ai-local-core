'use client';

import React from 'react';

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
  className = '',
}: CapabilityWorkbenchCommandHeaderProps) {
  const placement = useCapabilityWorkbenchPlacement();
  const mobileFloatingControls = useOptionalCapabilityWorkbenchMobileFloatingControls();
  const useCompactMobileLayout = mobileVariant === 'compact' && placement === 'mobile';
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

  if (useCompactMobileLayout) {
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
      >
        <div className="flex min-w-0 items-start gap-2">
          <SlotFrame
            className="min-w-0 flex-1"
            testId="capability-workbench-command-header-brand"
          >
            {brandSlot}
          </SlotFrame>
          <SlotFrame
            className="shrink-0"
            testId="capability-workbench-command-header-utility"
          >
            {externalizeUtilitySlot ? null : utilitySlot}
          </SlotFrame>
        </div>
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
