'use client';

import React from 'react';
import ConfirmDialog from '@/components/ConfirmDialog';

export interface RestartConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  t: (key: string, params?: any) => string;
}

export default function RestartConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  t,
}: RestartConfirmDialogProps) {
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title={t('confirmRestartExecution' as any) || 'Confirm Restart Execution'}
      message={t('confirmRestartExecutionMessage' as any) || 'Are you sure you want to restart this execution? This will create a new execution and cancel the current one.'}
      confirmText={t('accept' as any) || '確定'}
      cancelText={t('cancel' as any) || '取消'}
      confirmButtonClassName="bg-blue-600 hover:bg-blue-700"
    />
  );
}
