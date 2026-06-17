'use client';

import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

import { useCapabilityWorkbenchPlacement } from './CapabilityWorkbenchResponsiveFrame';

interface CapabilityWorkbenchMenuWrapProps {
  ariaLabel: string;
  activeLabel?: string;
  primarySlot: React.ReactNode;
  secondarySlot?: React.ReactNode;
  trailingSlot?: React.ReactNode;
  mobileDefaultCollapsed?: boolean;
  className?: string;
  contentClassName?: string;
  testId?: string;
}

export function CapabilityWorkbenchMenuWrap({
  ariaLabel,
  activeLabel,
  primarySlot,
  secondarySlot,
  trailingSlot,
  mobileDefaultCollapsed = true,
  className = '',
  contentClassName = '',
  testId = 'capability-workbench-menu-wrap',
}: CapabilityWorkbenchMenuWrapProps) {
  const placement = useCapabilityWorkbenchPlacement();
  const [mobileCollapsed, setMobileCollapsed] = React.useState(mobileDefaultCollapsed);
  const isMobile = placement === 'mobile';

  React.useEffect(() => {
    setMobileCollapsed(isMobile ? mobileDefaultCollapsed : false);
  }, [isMobile, mobileDefaultCollapsed]);

  if (!isMobile) {
    return (
      <div
        className={className}
        data-testid={testId}
        data-workbench-menu-wrap="true"
        data-workbench-placement={placement}
        aria-label={ariaLabel}
      >
        <div className={contentClassName} data-testid={`${testId}-content`}>
          {primarySlot}
          {secondarySlot}
          {trailingSlot}
        </div>
      </div>
    );
  }

  return (
    <section
      className={className}
      data-testid={testId}
      data-workbench-menu-wrap="true"
      data-workbench-placement={placement}
      data-mobile-collapsed={mobileCollapsed ? 'true' : 'false'}
      aria-label={ariaLabel}
    >
      <div className="flex min-w-0 items-center justify-between gap-2">
        <div className="min-w-0 truncate text-xs font-semibold text-gray-600 dark:text-gray-300">
          {activeLabel || ariaLabel}
        </div>
        <button
          type="button"
          aria-label={mobileCollapsed ? `Expand ${ariaLabel}` : `Collapse ${ariaLabel}`}
          aria-expanded={!mobileCollapsed}
          onClick={() => setMobileCollapsed((current) => !current)}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-gray-200 bg-white/80 text-gray-600 transition hover:border-blue-300 hover:text-blue-700 dark:border-gray-700 dark:bg-gray-900/70 dark:text-gray-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
          data-testid={`${testId}-toggle`}
        >
          {mobileCollapsed ? (
            <ChevronDown aria-hidden className="h-4 w-4" />
          ) : (
            <ChevronUp aria-hidden className="h-4 w-4" />
          )}
        </button>
      </div>
      {mobileCollapsed ? null : (
        <div className={`mt-2 ${contentClassName}`} data-testid={`${testId}-content`}>
          {primarySlot}
          {secondarySlot}
          {trailingSlot}
        </div>
      )}
    </section>
  );
}

export default CapabilityWorkbenchMenuWrap;
