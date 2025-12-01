'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface ContextCardProps {
  context: {
    workspace_focus?: string | null;
    workspace_focus_key?: string | null;
    recent_file?: {
      name: string;
      uploaded_at: string;
    } | null;
    detected_intents: Array<{
      id: string;
      title: string;
      source: string;
      status: string;
    }>;
  };
  showRecentFile?: boolean;
  showDetectedIntents?: boolean;
}

export default function ContextCard({ context, showRecentFile = true, showDetectedIntents = true }: ContextCardProps) {
  return (
    <div className="bg-white border rounded p-2 shadow-sm">
      <h3 className="font-semibold text-xs text-gray-900 mb-2">{t('currentContext')}</h3>

      <div className="space-y-2">
        {/* 本工作空间目前在做什么 */}
        <div>
          <div className="text-[10px] text-gray-500 mb-0.5">{t('workspaceCurrentlyDoing') || '本工作空間目前在處理'}</div>
          <div className="text-xs text-gray-900 font-medium">
            {context.workspace_focus ? (
              <span className="animate-fade-in">{context.workspace_focus}</span>
            ) : (
              <span className="text-gray-400">{context.workspace_focus_key ? t(context.workspace_focus_key as any) : t('noClearWorkspaceFocus')}</span>
            )}
          </div>
        </div>

        {context.recent_file && (
          <div
            className={`transition-opacity duration-500 ease-in ${
              showRecentFile ? 'opacity-100' : 'opacity-0'
            }`}
            style={{ display: showRecentFile ? 'block' : 'none' }}
          >
            <div className="text-[10px] text-gray-500 mb-0.5">{t('recentUploadedFile')}</div>
            <div className="text-xs text-gray-900">
              {context.recent_file.name}
            </div>
            <div className="text-[10px] text-gray-400 mt-0.5">
              {new Date(context.recent_file.uploaded_at).toLocaleString('zh-TW')}
            </div>
          </div>
        )}

        {context.detected_intents && context.detected_intents.length > 0 && (
          <div
            className={`transition-opacity duration-500 ease-in ${
              showDetectedIntents ? 'opacity-100' : 'opacity-0'
            }`}
            style={{ display: showDetectedIntents ? 'block' : 'none' }}
          >
            <div className="text-[10px] text-gray-500 mb-0.5">{t('detectedIntents')}</div>
            <div className="space-y-0.5">
              {context.detected_intents.map((intent) => (
                <div
                  key={intent.id}
                  className="text-xs text-gray-900 bg-gray-50 rounded px-1.5 py-0.5"
                >
                  {intent.title}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
