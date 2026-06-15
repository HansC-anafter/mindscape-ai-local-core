'use client';

import React from 'react';

export type CapabilityWorkbenchPlacement = 'desktop' | 'mobile';

export const CAPABILITY_WORKBENCH_MOBILE_QUERY = '(max-width: 767px)';
export const CAPABILITY_WORKBENCH_VIEWPORT_CLASS = 'flex h-dvh min-h-0 flex-col overflow-hidden';
export const CAPABILITY_WORKBENCH_SHELL_CLASS =
  'relative flex min-h-0 flex-1 flex-col overflow-hidden md:flex-row';

export function getCapabilityWorkbenchPlacement(): CapabilityWorkbenchPlacement {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'desktop';
  }
  return window.matchMedia(CAPABILITY_WORKBENCH_MOBILE_QUERY).matches ? 'mobile' : 'desktop';
}

export function useCapabilityWorkbenchPlacement(): CapabilityWorkbenchPlacement {
  const [placement, setPlacement] = React.useState<CapabilityWorkbenchPlacement>(() => (
    getCapabilityWorkbenchPlacement()
  ));

  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const query = window.matchMedia(CAPABILITY_WORKBENCH_MOBILE_QUERY);
    const updatePlacement = () => {
      setPlacement(query.matches ? 'mobile' : 'desktop');
    };

    updatePlacement();
    query.addEventListener('change', updatePlacement);
    return () => query.removeEventListener('change', updatePlacement);
  }, []);

  return placement;
}

export function getCapabilityWorkbenchShellClassName(className?: string): string {
  return [CAPABILITY_WORKBENCH_SHELL_CLASS, className].filter(Boolean).join(' ');
}

export function getCapabilityWorkbenchNavigationRegionClassName(): string {
  return [
    'order-2 flex shrink-0 overflow-hidden border-t border-gray-200 bg-white/95 dark:border-zinc-800 dark:bg-zinc-950/95',
    'md:order-none md:min-h-0 md:border-t-0 md:bg-transparent md:dark:bg-transparent',
  ].join(' ');
}

export function getCapabilityWorkbenchNavigationSlotClassName(showNavigation: boolean): string {
  const mobileOpenClassName = showNavigation
    ? 'pointer-events-auto max-h-[70dvh] opacity-100'
    : 'pointer-events-none max-h-0 opacity-0';
  const desktopOpenClassName = showNavigation
    ? 'md:w-64 md:opacity-100'
    : 'md:w-0 md:opacity-0';

  return [
    'fixed inset-x-2 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-40 min-h-0 overflow-hidden rounded-t-lg border border-gray-200 bg-white shadow-xl transition-[max-height,width,opacity] duration-200 ease-[cubic-bezier(0.2,0.8,0.2,1)] dark:border-zinc-800 dark:bg-zinc-950',
    mobileOpenClassName,
    'md:static md:inset-auto md:z-auto md:rounded-none md:border-0 md:bg-transparent md:shadow-none md:transition-[width,opacity]',
    desktopOpenClassName,
  ].join(' ');
}

export function getPackScopeToolRailClassName(placement: CapabilityWorkbenchPlacement): string {
  if (placement === 'mobile') {
    return 'flex min-h-[52px] w-full shrink-0 items-center border-t border-gray-200 bg-zinc-50/95 px-2 py-1 pb-[calc(0.25rem+env(safe-area-inset-bottom))] shadow-[0_-1px_0_rgba(0,0,0,0.02)] dark:border-zinc-800 dark:bg-zinc-950';
  }
  return 'flex h-full min-h-0 w-9 shrink-0 flex-col border-r border-gray-200 bg-zinc-50/95 shadow-[inset_-1px_0_0_rgba(0,0,0,0.02)] dark:border-zinc-800 dark:bg-zinc-950';
}

export function getPackScopeToolListClassName(placement: CapabilityWorkbenchPlacement): string {
  if (placement === 'mobile') {
    return 'min-w-0 flex-1 overflow-x-auto overscroll-contain px-1 py-0.5';
  }
  return 'min-h-0 flex-1 overflow-y-auto overscroll-contain px-0.5 py-1.5';
}

export function getPackScopeToolListInnerClassName(placement: CapabilityWorkbenchPlacement): string {
  if (placement === 'mobile') {
    return 'flex min-w-max items-center justify-end gap-1';
  }
  return 'flex flex-col items-center gap-0.5';
}

export function getPackScopeToolPanelClassName(
  placement: CapabilityWorkbenchPlacement,
  panelExpanded: boolean,
): string {
  if (placement === 'mobile') {
    return 'fixed inset-x-2 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] z-40 max-h-[70dvh] overflow-hidden rounded-t-lg border border-zinc-800 bg-zinc-950/95 text-zinc-100 shadow-xl shadow-black/25 backdrop-blur-sm';
  }
  return `fixed z-40 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/95 text-zinc-100 shadow-xl shadow-black/25 backdrop-blur-sm ${
    panelExpanded ? 'w-[280px]' : 'max-w-[340px]'
  }`;
}
