'use client';

import React, { useEffect, ReactNode } from 'react';
import { t } from '../lib/i18n';

interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  maxWidth?: string;
}

export function BaseModal({
  isOpen,
  onClose,
  title,
  children,
  maxWidth = 'max-w-4xl'
}: BaseModalProps) {
  // ESC键关闭弹窗
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      // 防止背景滚动
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  // 点击背景关闭弹窗
  const handleBackdropClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className={`bg-surface-accent dark:bg-gray-800 rounded-lg shadow-xl ${maxWidth} w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col`}>
        {/* Modal Header */}
        <div className="flex items-center justify-between p-6 border-b border-default dark:border-gray-700 flex-shrink-0">
          <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="text-secondary dark:text-gray-500 hover:text-primary dark:hover:text-gray-300 text-2xl leading-none w-8 h-8 flex items-center justify-center rounded-md hover:bg-surface-secondary dark:hover:bg-gray-700 transition-colors"
            aria-label={t('closeModal')}
          >
            ×
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto flex-1 min-h-0">
          {children}
        </div>
      </div>
    </div>
  );
}
