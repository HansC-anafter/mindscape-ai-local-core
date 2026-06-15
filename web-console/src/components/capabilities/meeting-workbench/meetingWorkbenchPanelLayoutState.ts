'use client';

import React from 'react';

import type { InspectorTab, MeetingInfoPanel } from './meetingWorkbenchTypes';

export type MeetingWorkbenchViewportClass = 'mobile' | 'tablet' | 'desktop';
export type MeetingWorkbenchSecondarySurface = MeetingInfoPanel | 'inspector' | 'console';
export type MeetingWorkbenchPanePreset = 'compact' | 'default' | 'expanded';

export const MEETING_WORKBENCH_MOBILE_QUERY = '(max-width: 767px)';
export const MEETING_WORKBENCH_TABLET_QUERY = '(min-width: 768px) and (max-width: 1023px)';

export function classifyMeetingWorkbenchViewportWidth(width: number): MeetingWorkbenchViewportClass {
  if (width < 768) {
    return 'mobile';
  }
  if (width < 1024) {
    return 'tablet';
  }
  return 'desktop';
}

export function getMeetingWorkbenchViewportClass(): MeetingWorkbenchViewportClass {
  if (typeof window === 'undefined') {
    return 'desktop';
  }

  if (typeof window.matchMedia === 'function') {
    if (window.matchMedia(MEETING_WORKBENCH_MOBILE_QUERY).matches) {
      return 'mobile';
    }
    if (window.matchMedia(MEETING_WORKBENCH_TABLET_QUERY).matches) {
      return 'tablet';
    }
    return 'desktop';
  }

  return classifyMeetingWorkbenchViewportWidth(window.innerWidth);
}

export function useMeetingWorkbenchViewportClass(): MeetingWorkbenchViewportClass {
  const [viewportClass, setViewportClass] = React.useState<MeetingWorkbenchViewportClass>(() => (
    getMeetingWorkbenchViewportClass()
  ));

  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mobileQuery = window.matchMedia(MEETING_WORKBENCH_MOBILE_QUERY);
    const tabletQuery = window.matchMedia(MEETING_WORKBENCH_TABLET_QUERY);
    const updateViewportClass = () => {
      setViewportClass(getMeetingWorkbenchViewportClass());
    };

    updateViewportClass();
    mobileQuery.addEventListener('change', updateViewportClass);
    tabletQuery.addEventListener('change', updateViewportClass);
    window.addEventListener('resize', updateViewportClass);

    return () => {
      mobileQuery.removeEventListener('change', updateViewportClass);
      tabletQuery.removeEventListener('change', updateViewportClass);
      window.removeEventListener('resize', updateViewportClass);
    };
  }, []);

  return viewportClass;
}

export function isCompactMeetingWorkbenchViewport(
  viewportClass: MeetingWorkbenchViewportClass,
): boolean {
  return viewportClass !== 'desktop';
}

export function getMeetingWorkbenchDefaultPanePreset(
  viewportClass: MeetingWorkbenchViewportClass,
): MeetingWorkbenchPanePreset {
  return viewportClass === 'desktop' ? 'default' : 'expanded';
}

export function resolveMeetingWorkbenchSecondarySurface({
  activeInfoPanel,
  activeInspector,
  isConsoleOpen,
}: {
  activeInfoPanel: MeetingInfoPanel | null;
  activeInspector: InspectorTab | null;
  isConsoleOpen: boolean;
}): MeetingWorkbenchSecondarySurface | null {
  if (activeInfoPanel) {
    return activeInfoPanel;
  }
  if (activeInspector) {
    return 'inspector';
  }
  if (isConsoleOpen) {
    return 'console';
  }
  return null;
}
