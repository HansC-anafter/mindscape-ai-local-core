import type { ReactNode } from 'react';

interface MeetingWorkbenchSecondaryDrawerProps {
  label: string;
  surface: string;
  onClose: () => void;
  children: ReactNode;
}

export function MeetingWorkbenchSecondaryDrawer({
  label,
  surface,
  onClose,
  children,
}: MeetingWorkbenchSecondaryDrawerProps) {
  return (
    <>
      <button
        type="button"
        className="absolute inset-0 z-30 bg-slate-950/20 backdrop-blur-[1px] md:bg-slate-950/10"
        aria-label={`Close ${label}`}
        data-testid="meeting-secondary-drawer-backdrop"
        onClick={onClose}
      />
      <section
        className="absolute inset-x-3 bottom-3 top-3 z-40 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950 md:left-auto md:w-[360px]"
        aria-label={label}
        data-testid="meeting-secondary-drawer"
        data-secondary-surface={surface}
      >
        {children}
      </section>
    </>
  );
}
