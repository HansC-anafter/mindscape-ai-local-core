'use client';

import React from 'react';

import { useT } from '@/lib/i18n';

interface RejectTaskDialogProps {
  taskId: string | null;
  rejectReason: string;
  rejectComment: string;
  onRejectReasonChange: (value: string) => void;
  onRejectCommentChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
}

export default function RejectTaskDialog({
  taskId,
  rejectReason,
  rejectComment,
  onRejectReasonChange,
  onRejectCommentChange,
  onCancel,
  onConfirm,
}: RejectTaskDialogProps) {
  const t = useT();

  if (!taskId) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('rejectTask' as any)}
        </h3>
        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
          {t('rejectTaskConfirm' as any)}
        </p>

        <div className="mb-4">
          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('rejectReason' as any)}
          </label>
          <select
            value={rejectReason}
            onChange={(event) => onRejectReasonChange(event.target.value)}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
          >
            <option value="">{t('rejectReasonOther' as any)}</option>
            <option value="irrelevant">{t('rejectReasonIrrelevant' as any)}</option>
            <option value="duplicate">{t('rejectReasonDuplicate' as any)}</option>
            <option value="dont_want_auto">{t('rejectReasonDontWantAuto' as any)}</option>
            <option value="other">{t('rejectReasonOther' as any)}</option>
          </select>
        </div>

        {rejectReason === 'other' ? (
          <div className="mb-4">
            <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('rejectComment' as any)}
            </label>
            <textarea
              value={rejectComment}
              onChange={(event) => onRejectCommentChange(event.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
              rows={3}
              placeholder={t('rejectComment' as any)}
            />
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
          >
            {t('cancel' as any)}
          </button>
          <button
            onClick={() => void onConfirm()}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
          >
            {t('reject' as any)}
          </button>
        </div>
      </div>
    </div>
  );
}
