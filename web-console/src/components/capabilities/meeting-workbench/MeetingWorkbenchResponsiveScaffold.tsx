import type { ReactNode } from 'react';

import {
  isCompactMeetingWorkbenchViewport,
  type MeetingWorkbenchViewportClass,
} from './meetingWorkbenchPanelLayoutState';

interface MeetingWorkbenchResponsiveScaffoldProps {
  viewportClass: MeetingWorkbenchViewportClass;
  header: ReactNode;
  floatingPanel?: ReactNode;
  stage: ReactNode;
  secondaryDrawer?: ReactNode;
  inlineConsole?: ReactNode;
  notification?: ReactNode;
  commandBar: ReactNode;
  dispatchError?: ReactNode;
}

export function MeetingWorkbenchResponsiveScaffold({
  viewportClass,
  header,
  floatingPanel = null,
  stage,
  secondaryDrawer = null,
  inlineConsole = null,
  notification = null,
  commandBar,
  dispatchError = null,
}: MeetingWorkbenchResponsiveScaffoldProps) {
  const compactViewport = isCompactMeetingWorkbenchViewport(viewportClass);

  return (
    <div
      className="flex h-full min-h-0 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="meeting-workbench-responsive-scaffold"
      data-workbench-viewport={viewportClass}
    >
      <div className="flex min-w-0 flex-1 flex-col">
        {header}
        <div className="relative flex min-h-0 flex-1">
          {!compactViewport ? floatingPanel : null}
          {stage}
          {compactViewport ? secondaryDrawer : null}
        </div>
        {!compactViewport ? inlineConsole : null}
        {notification}
        {commandBar}
        {dispatchError}
      </div>
    </div>
  );
}
