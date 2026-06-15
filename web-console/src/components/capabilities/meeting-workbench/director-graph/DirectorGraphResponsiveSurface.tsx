import type { ReactNode } from 'react';

import { Braces, Layers, SlidersHorizontal } from 'lucide-react';

import { MeetingWorkbenchSecondaryDrawer } from '../MeetingWorkbenchSecondaryDrawer';
import {
  isCompactMeetingWorkbenchViewport,
  type MeetingWorkbenchViewportClass,
} from '../meetingWorkbenchPanelLayoutState';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export type DirectorGraphSecondarySurface = 'palette' | 'inspector' | 'json';

interface DirectorGraphResponsiveSurfaceProps {
  viewportClass: MeetingWorkbenchViewportClass;
  title: string;
  status: string;
  palette: ReactNode;
  canvas: ReactNode;
  inspector: ReactNode;
  importExport: ReactNode;
  diagnostics?: ReactNode;
  desktopToolbar: ReactNode;
  compactPrimaryActions: ReactNode;
  compactUtilityActions: ReactNode;
  compactSurface: DirectorGraphSecondarySurface | null;
  onCloseCompactSurface: () => void;
  t: MeetingTranslate;
}

const SURFACE_ICON = {
  palette: Layers,
  inspector: SlidersHorizontal,
  json: Braces,
} satisfies Record<DirectorGraphSecondarySurface, typeof Layers>;

const SURFACE_LABEL_KEY = {
  palette: 'directorGraphPalette',
  inspector: 'directorGraphInspector',
  json: 'directorGraphJsonTitle',
} as const;

export function DirectorGraphResponsiveSurface({
  viewportClass,
  title,
  status,
  palette,
  canvas,
  inspector,
  importExport,
  diagnostics = null,
  desktopToolbar,
  compactPrimaryActions,
  compactUtilityActions,
  compactSurface,
  onCloseCompactSurface,
  t,
}: DirectorGraphResponsiveSurfaceProps) {
  const compactViewport = isCompactMeetingWorkbenchViewport(viewportClass);
  const CompactSurfaceIcon = compactSurface ? SURFACE_ICON[compactSurface] : null;
  const compactSurfaceLabel = compactSurface ? t(SURFACE_LABEL_KEY[compactSurface]) : '';

  return (
    <section
      className="flex min-h-0 flex-1 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="director-graph-canvas"
      data-workbench-viewport={viewportClass}
    >
      {!compactViewport ? palette : null}
      <div className="flex min-w-0 flex-1 flex-col">
        {!compactViewport ? (
          <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-950">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
              <div className="truncate text-xs text-slate-500 dark:text-slate-400">{status}</div>
            </div>
            {desktopToolbar}
          </div>
        ) : (
          <div className="border-b border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
                <div className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">{status}</div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">{compactPrimaryActions}</div>
            </div>
            <div className="-mx-1 mt-3 overflow-x-auto pb-1">
              <div className="flex min-w-max items-center gap-1.5 px-1">{compactUtilityActions}</div>
            </div>
          </div>
        )}

        <div className="relative min-h-0 flex-1">
          {canvas}
          {compactViewport && compactSurface && CompactSurfaceIcon ? (
            <MeetingWorkbenchSecondaryDrawer
              label={compactSurfaceLabel}
              surface={compactSurface}
              onClose={onCloseCompactSurface}
            >
              <div className="flex h-full min-h-0 flex-col">
                <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  <CompactSurfaceIcon className="h-4 w-4" aria-hidden="true" />
                  {compactSurfaceLabel}
                </div>
                <div className="min-h-0 flex-1">
                  {compactSurface === 'palette' ? palette : null}
                  {compactSurface === 'inspector' ? inspector : null}
                  {compactSurface === 'json' ? importExport : null}
                </div>
              </div>
            </MeetingWorkbenchSecondaryDrawer>
          ) : null}
        </div>

        {!compactViewport ? importExport : null}
        {diagnostics}
      </div>
      {!compactViewport ? inspector : null}
    </section>
  );
}
