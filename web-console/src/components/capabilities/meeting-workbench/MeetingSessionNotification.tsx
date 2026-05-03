import React from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

import type { MeetingSessionNotificationDetail } from './meetingSessionNotifications';

const toneClasses: Record<MeetingSessionNotificationDetail['tone'], string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-200',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200',
  warning: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200',
  error: 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-200',
};

const icons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

export function MeetingSessionNotification({
  notification,
  dismissLabel,
  onClose,
}: {
  notification: MeetingSessionNotificationDetail;
  dismissLabel: string;
  onClose: () => void;
}) {
  const Icon = icons[notification.tone];
  return (
    <div
      aria-live="polite"
      className={`mx-3 mb-2 flex shrink-0 items-start gap-2 rounded-md border px-3 py-2 text-xs ${toneClasses[notification.tone]}`}
      data-testid="meeting-session-notification"
      data-tone={notification.tone}
      role={notification.tone === 'error' ? 'alert' : 'status'}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{notification.title}</div>
        <div className="mt-0.5 truncate opacity-85">{notification.message}</div>
      </div>
      <button
        type="button"
        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded hover:bg-black/5 dark:hover:bg-white/10"
        aria-label={dismissLabel}
        onClick={onClose}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
