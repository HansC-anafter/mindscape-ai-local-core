import React, { type ComponentProps, type ReactNode } from 'react';

import { MeetingCommandBar } from './CommandDock';
import { MeetingSessionNotification } from './MeetingSessionNotification';
import { MeetingWorkbenchResponsiveScaffold } from './MeetingWorkbenchResponsiveScaffold';
import { MeetingWorkbenchStage } from './MeetingWorkbenchStage';
import { MeetingHeaderToolbar } from './SemanticFlowCanvas';
import type { MeetingWorkbenchViewportClass } from './meetingWorkbenchPanelLayoutState';

export interface MeetingWorkbenchStageLayoutProps {
  viewportClass: MeetingWorkbenchViewportClass;
  headerProps: ComponentProps<typeof MeetingHeaderToolbar>;
  floatingPanel: ReactNode;
  stageProps: ComponentProps<typeof MeetingWorkbenchStage>;
  secondaryDrawer: ReactNode;
  inlineConsole: ReactNode;
  notificationProps: ComponentProps<typeof MeetingSessionNotification> | null;
  commandBarProps: ComponentProps<typeof MeetingCommandBar>;
  dispatchError: string | null;
}

export function MeetingWorkbenchStageLayout({
  viewportClass,
  headerProps,
  floatingPanel,
  stageProps,
  secondaryDrawer,
  inlineConsole,
  notificationProps,
  commandBarProps,
  dispatchError,
}: MeetingWorkbenchStageLayoutProps) {
  return (
    <MeetingWorkbenchResponsiveScaffold
      viewportClass={viewportClass}
      header={<MeetingHeaderToolbar {...headerProps} />}
      floatingPanel={floatingPanel}
      stage={<MeetingWorkbenchStage {...stageProps} />}
      secondaryDrawer={secondaryDrawer}
      inlineConsole={inlineConsole}
      notification={notificationProps ? <MeetingSessionNotification {...notificationProps} /> : null}
      commandBar={<MeetingCommandBar {...commandBarProps} />}
      dispatchError={dispatchError ? (
        <div
          className="border-t border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300"
          data-testid="meeting-dispatch-error"
        >
          {dispatchError}
        </div>
      ) : null}
    />
  );
}
