'use client';

import React from 'react';
import { Chapter } from '@/lib/story-thread-api';

interface ChapterCardProps {
  chapter: Chapter;
  isCurrent?: boolean;
  onSelect?: (chapterId: string) => void;
  onUpdate?: (chapterId: string, updates: Partial<Chapter>) => void;
}

export function ChapterCard({ chapter, isCurrent, onSelect, onUpdate }: ChapterCardProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'planned':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return '已完成';
      case 'in_progress':
        return '進行中';
      case 'planned':
        return '計劃中';
      default:
        return status;
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleString('zh-TW', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div
      className={`chapter-card p-4 rounded-lg border-2 transition-all ${
        isCurrent
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-200 hover:border-gray-300'
      } ${onSelect ? 'cursor-pointer' : ''}`}
      onClick={() => onSelect?.(chapter.chapter_id)}
    >
      <div className="chapter-header flex items-start justify-between mb-2">
        <div className="flex-1">
          <h4 className="text-lg font-semibold text-gray-900 mb-1">
            {chapter.name}
            {isCurrent && (
              <span className="ml-2 text-xs text-blue-600">(當前)</span>
            )}
          </h4>
          {chapter.description && (
            <p className="text-sm text-gray-600 mb-2">{chapter.description}</p>
          )}
        </div>
        <span className={`status-badge px-2 py-1 rounded text-xs font-medium ${getStatusColor(chapter.status)}`}>
          {getStatusLabel(chapter.status)}
        </span>
      </div>

      <div className="chapter-details space-y-2 text-sm text-gray-600">
        {chapter.playbooks_used.length > 0 && (
          <div className="playbooks">
            <span className="font-medium">使用的 Playbooks: </span>
            <span>{chapter.playbooks_used.join(', ')}</span>
          </div>
        )}

        {chapter.artifacts.length > 0 && (
          <div className="artifacts">
            <span className="font-medium">產出: </span>
            <span>{chapter.artifacts.length} 個 Artifacts</span>
          </div>
        )}

        <div className="dates flex gap-4 text-xs text-gray-500">
          <div>
            <span className="font-medium">創建: </span>
            {formatDate(chapter.created_at)}
          </div>
          {chapter.completed_at && (
            <div>
              <span className="font-medium">完成: </span>
              {formatDate(chapter.completed_at)}
            </div>
          )}
        </div>

        {Object.keys(chapter.context_additions).length > 0 && (
          <div className="context-additions mt-2 p-2 bg-gray-50 rounded text-xs">
            <span className="font-medium">上下文更新: </span>
            <pre className="mt-1 text-gray-600">
              {JSON.stringify(chapter.context_additions, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default ChapterCard;

