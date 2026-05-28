'use client';

import React from 'react';

import type { CapabilityWorkbenchCommandHeaderProps } from '@/types/capability-workbench';

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
  className = '',
}: CapabilityWorkbenchCommandHeaderProps) {
  return (
    <header
      className={`flex min-h-[56px] shrink-0 items-center gap-3 border-b border-stone-800 bg-stone-950 px-3 py-2 text-stone-100 ${className}`.trim()}
      data-testid="capability-workbench-command-header"
    >
      <SlotFrame
        className="w-[220px] shrink-0"
        testId="capability-workbench-command-header-brand"
      >
        {brandSlot}
      </SlotFrame>
      <SlotFrame
        className="shrink-0"
        testId="capability-workbench-command-header-mode"
      >
        {modeSlot}
      </SlotFrame>
      <SlotFrame
        className="shrink-0"
        testId="capability-workbench-command-header-primary-toolbar"
      >
        {primaryToolbarSlot}
      </SlotFrame>
      <SlotFrame
        className="min-w-[160px] flex-1"
        testId="capability-workbench-command-header-context-toolbar"
      >
        {contextToolbarSlot}
      </SlotFrame>
      <SlotFrame
        className="shrink-0"
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
