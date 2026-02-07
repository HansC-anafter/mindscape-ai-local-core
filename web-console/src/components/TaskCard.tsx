'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface TaskCardProps {
  taskNumber: number;
  title: string;
  subtitle: string;
  isCompleted: boolean;
  isBlocked?: boolean;
  blockMessage?: string;
  completedContent?: React.ReactNode;
  uncompletedContent: React.ReactNode;
  buttonText: string;
  onButtonClick: () => void;
  footerText?: string;
}

export default function TaskCard({
  taskNumber,
  title,
  subtitle,
  isCompleted,
  isBlocked = false,
  blockMessage,
  completedContent,
  uncompletedContent,
  buttonText,
  onButtonClick,
  footerText
}: TaskCardProps) {

  return (
    <div className={`bg-white shadow rounded-lg p-6 transition-all duration-300 ${
      isCompleted ? 'border-2 border-green-300' : 'border border-gray-200'
    }`}>
      {/* Header */}
      <div className="flex items-center mb-3">
        {isCompleted ? (
          <span className="text-2xl mr-2">✅</span>
        ) : (
          <span className="text-2xl mr-2">🔒</span>
        )}
        <div>
          <h3 className="text-lg font-semibold text-gray-900">
            {isCompleted ? title : `${t('taskLabel' as any)} ${taskNumber}：${title}`}
          </h3>
          <p className="text-sm text-gray-600">{subtitle}</p>
        </div>
      </div>

      {/* Content */}
      <div className="mb-4">
        {isCompleted ? (
          completedContent || (
            <p className="text-sm text-gray-500">{t('taskCompleted' as any)}</p>
          )
        ) : (
          <div>
            {uncompletedContent}
            {isBlocked && blockMessage && (
              <div className="mt-3 flex items-start">
                <span className="text-yellow-500 mr-2">💡</span>
                <p className="text-sm text-gray-600">{blockMessage}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action button */}
      <button
        onClick={onButtonClick}
        disabled={isBlocked}
        className={`w-full px-4 py-2 rounded-md text-sm font-medium transition-colors ${
          isCompleted
            ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            : isBlocked
            ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
            : 'bg-gray-600 text-white hover:bg-gray-700'
        }`}
      >
        {buttonText}
      </button>

      {/* Footer hint */}
      {footerText && (
        <div className="mt-3 text-xs text-gray-500 text-center">
          {footerText}
        </div>
      )}
    </div>
  );
}
