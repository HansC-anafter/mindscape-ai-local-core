import type { MeetingWorkbenchViewportClass } from './meetingWorkbenchPanelLayoutState';

function normalizeSurfaceRoute(surfaceRoute: string | null | undefined): string {
  return String(surfaceRoute || '').toLowerCase();
}

export function shouldPreferRunsOnCompactRemoteSurface({
  viewportClass,
  surfaceRoute,
}: {
  viewportClass: MeetingWorkbenchViewportClass;
  surfaceRoute?: string | null;
}): boolean {
  if (viewportClass === 'desktop') {
    return false;
  }
  const normalizedRoute = normalizeSurfaceRoute(surfaceRoute);
  return normalizedRoute.includes('/capability-ui-hosts/');
}
