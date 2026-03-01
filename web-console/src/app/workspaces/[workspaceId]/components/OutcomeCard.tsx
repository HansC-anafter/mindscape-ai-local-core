'use client';

import React from 'react';
import { Artifact } from './OutcomesPanel';
import { formatLocalDateTime } from '@/lib/time';

interface OutcomeCardProps {
  artifact: Artifact;
  onArtifactClick?: (artifact: Artifact) => void;
  onCopy?: (artifact: Artifact, e: React.MouseEvent) => void;
  onOpenExternal?: (artifact: Artifact, e: React.MouseEvent) => void;
  onDownload?: (artifact: Artifact, e: React.MouseEvent) => void;
  onNavigate?: (artifact: Artifact, e: React.MouseEvent) => void;
  isHighlighted?: boolean;
}

const getArtifactIcon = (artifactType: string): string => {
  const iconMap: Record<string, string> = {
    checklist: '✅',
    draft: '📝',
    config: '⚙️',
    canva: '🎨',
    audio: '🔊',
    docx: '📄',
    file: '📁',
    link: '🔗',
    post: '📱',
    image: '🖼️',
    video: '🎬',
    code: '💻',
    data: '📊'
  };
  return iconMap[artifactType] || '📦';
};

const getArtifactTypeLabel = (artifactType: string): string => {
  const labelMap: Record<string, string> = {
    checklist: '清單',
    draft: '草稿',
    config: '設定',
    canva: 'Canva',
    audio: '音頻',
    docx: '文件',
    file: '文件',
    link: '連結',
    post: '貼文',
    image: '圖片',
    video: '視頻',
    code: '代碼',
    data: '數據'
  };
  return labelMap[artifactType] || artifactType;
};

const formatFileSize = (bytes?: number): string => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export default function OutcomeCard({
  artifact,
  onArtifactClick,
  onCopy,
  onOpenExternal,
  onDownload,
  onNavigate,
  isHighlighted = false
}: OutcomeCardProps) {
  const handleCardClick = () => {
    if (onArtifactClick) {
      onArtifactClick(artifact);
    }
  };

  const handleActionClick = (e: React.MouseEvent, handler?: (artifact: Artifact, e: React.MouseEvent) => void) => {
    e.stopPropagation();
    if (handler) {
      handler(artifact, e);
    }
  };

  const metadata = artifact.metadata || {};
  const fileSize = metadata.file_size ? formatFileSize(metadata.file_size) : null;
  const platform = metadata.platform || null;
  const externalUrl = metadata.external_url || artifact.storage_ref || null;

  return (
    <div
      onClick={handleCardClick}
      className={`
        bg-white dark:bg-gray-800 border rounded-lg p-3 hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-md transition-all cursor-pointer
        ${isHighlighted
          ? 'border-blue-400 dark:border-blue-500 shadow-lg bg-blue-50 dark:bg-blue-900/20 animate-pulse'
          : 'border-gray-200 dark:border-gray-700'
        }
      `}
      style={isHighlighted ? {
        animation: 'fadeInHighlight 0.5s ease-in-out'
      } : undefined}
    >
      {/* Header */}
      <div className="flex items-start gap-2 mb-2">
        <span className="text-xl flex-shrink-0">{getArtifactIcon(artifact.artifact_type)}</span>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">{artifact.title}</h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{artifact.summary}</p>
        </div>
      </div>

      {/* Meta Info */}
      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 mb-2 flex-wrap">
        <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-[10px]">
          {getArtifactTypeLabel(artifact.artifact_type)}
        </span>
        {platform && (
          <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 rounded text-[10px]">
            {platform}
          </span>
        )}
        {fileSize && (
          <span className="text-[10px]">{fileSize}</span>
        )}
        <span className="text-[10px]">{formatLocalDateTime(artifact.created_at)}</span>
        {artifact.intent_id && (
          <span className="text-[10px] text-blue-500 dark:text-blue-400">來源 Intent</span>
        )}
      </div>

      {/* Quick Actions */}
      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        {artifact.primary_action_type === 'copy' && onCopy && (
          <button
            onClick={(e) => handleActionClick(e, onCopy)}
            className="px-2 py-1 text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors flex items-center gap-1"
            title="複製"
          >
            <span>📋</span>
            <span>複製</span>
          </button>
        )}
        {artifact.primary_action_type === 'open_external' && onOpenExternal && (
          <button
            onClick={(e) => handleActionClick(e, onOpenExternal)}
            className="px-2 py-1 text-xs bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors flex items-center gap-1"
            title="開啟"
          >
            <span>🔗</span>
            <span>開啟</span>
          </button>
        )}
        {artifact.primary_action_type === 'download' && onDownload && (
          <button
            onClick={(e) => handleActionClick(e, onDownload)}
            className="px-2 py-1 text-xs bg-gray-50 dark:bg-gray-800/30 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-100 dark:hover:bg-gray-800/40 transition-colors flex items-center gap-1"
            title="下載"
          >
            <span>⬇️</span>
            <span>下載</span>
          </button>
        )}
        {artifact.primary_action_type === 'navigate' && onNavigate && (
          <button
            onClick={(e) => handleActionClick(e, onNavigate)}
            className="px-2 py-1 text-xs bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded hover:bg-purple-100 dark:hover:bg-purple-900/40 transition-colors flex items-center gap-1"
            title="跳轉"
          >
            <span>➡️</span>
            <span>跳轉</span>
          </button>
        )}
        {externalUrl && artifact.primary_action_type !== 'open_external' && onOpenExternal && (
          <button
            onClick={(e) => handleActionClick(e, onOpenExternal)}
            className="px-2 py-1 text-xs bg-gray-50 dark:bg-gray-800/30 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-100 dark:hover:bg-gray-800/40 transition-colors flex items-center gap-1"
            title="開啟連結"
          >
            <span>🔗</span>
          </button>
        )}
      </div>
    </div>
  );
}

