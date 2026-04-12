'use client';

/**
 * Kanban View
 *
 * Features:
 * - Kanban component implementation
 * - Drag and drop to change status
 * - Card detail display
 */

import React, { useState, useEffect } from 'react';
import { parseServerTimestamp } from '@/lib/time';
import { GripVertical, FileText, CheckCircle2, Clock, Archive } from 'lucide-react';
import type { IGPost, PostStatus } from '../types';

interface KanbanViewProps {
  posts: IGPost[];
  selectedPostId: string | null;
  onPostSelect: (postId: string) => void;
  statusFilter: PostStatus | 'all';
  onStatusChange?: (postId: string, newStatus: PostStatus) => Promise<void>;
}

interface KanbanColumn {
  id: PostStatus | 'all';
  label: string;
  icon: React.ReactNode;
  color: string;
}

const columns: KanbanColumn[] = [
  {
    id: 'draft',
    label: 'Draft',
    icon: <FileText className="w-4 h-4" />,
    color: 'bg-gray-100 dark:bg-gray-700'
  },
  {
    id: 'review',
    label: 'In Review',
    icon: <Clock className="w-4 h-4" />,
    color: 'bg-yellow-100 dark:bg-yellow-900/20'
  },
  {
    id: 'ready',
    label: 'Ready',
    icon: <CheckCircle2 className="w-4 h-4" />,
    color: 'bg-blue-100 dark:bg-blue-900/20'
  },
  {
    id: 'scheduled',
    label: 'Scheduled',
    icon: <Clock className="w-4 h-4" />,
    color: 'bg-purple-100 dark:bg-purple-900/20'
  },
  {
    id: 'published',
    label: 'Published',
    icon: <CheckCircle2 className="w-4 h-4" />,
    color: 'bg-green-100 dark:bg-green-900/20'
  },
  {
    id: 'measured',
    label: 'Measured',
    icon: <Archive className="w-4 h-4" />,
    color: 'bg-indigo-100 dark:bg-indigo-900/20'
  }
];

export default function KanbanView({
  posts,
  selectedPostId,
  onPostSelect,
  statusFilter,
  onStatusChange
}: KanbanViewProps) {
  const [draggedPost, setDraggedPost] = useState<IGPost | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<PostStatus | null>(null);

  const filteredPosts = statusFilter === 'all'
    ? posts
    : posts.filter(post => post.status === statusFilter);

  const getPostsByStatus = (status: PostStatus): IGPost[] => {
    return filteredPosts.filter(post => post.status === status);
  };

  const handleDragStart = (e: React.DragEvent, post: IGPost) => {
    setDraggedPost(post);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', post.id);
  };

  const handleDragOver = (e: React.DragEvent, status: PostStatus) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverColumn(status);
  };

  const handleDragLeave = () => {
    setDragOverColumn(null);
  };

  const handleDrop = async (e: React.DragEvent, targetStatus: PostStatus) => {
    e.preventDefault();
    setDragOverColumn(null);

    if (!draggedPost || draggedPost.status === targetStatus) {
      setDraggedPost(null);
      return;
    }

    if (onStatusChange) {
      try {
        await onStatusChange(draggedPost.id, targetStatus);
      } catch (err) {
        console.error('Failed to change status:', err);
        alert(`Status change failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
    }

    setDraggedPost(null);
  };

  const formatDate = (dateString: string): string => {
    const date = parseServerTimestamp(dateString) ?? new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
  };

  const getPostPreview = (post: IGPost): string => {
    return post.text?.substring(0, 100) || post.artifact_id || 'No content';
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
          Kanban View
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Drag cards to different columns to change status
        </p>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden">
        <div className="flex gap-4 h-full min-w-max">
          {columns.map((column) => {
            const columnPosts = getPostsByStatus(column.id as PostStatus);
            const isDragOver = dragOverColumn === column.id;

            return (
              <div
                key={column.id}
                className="flex-shrink-0 w-72 flex flex-col"
                onDragOver={(e) => handleDragOver(e, column.id as PostStatus)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, column.id as PostStatus)}
              >
                <div className={`p-3 rounded-t-lg ${column.color} border-b border-gray-300 dark:border-gray-600`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      {column.icon}
                      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {column.label}
                      </span>
                    </div>
                    <span className="text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 px-2 py-0.5 rounded">
                      {columnPosts.length}
                    </span>
                  </div>
                </div>

                <div
                  className={`flex-1 overflow-y-auto p-2 space-y-2 rounded-b-lg bg-gray-50 dark:bg-gray-800/50 border border-t-0 border-gray-300 dark:border-gray-600 min-h-[400px] ${isDragOver ? 'ring-2 ring-blue-500 bg-blue-50 dark:bg-blue-900/20' : ''
                    }`}
                >
                  {columnPosts.map((post) => {
                    const isSelected = selectedPostId === post.id;
                    const isDragging = draggedPost?.id === post.id;

                    return (
                      <div
                        key={post.id}
                        draggable
                        onDragStart={(e) => handleDragStart(e, post)}
                        onClick={() => onPostSelect(post.id)}
                        className={`p-3 bg-white dark:bg-gray-800 rounded-lg border cursor-move hover:shadow-md transition-all ${isSelected
                            ? 'border-blue-500 ring-2 ring-blue-500'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                          } ${isDragging ? 'opacity-50' : ''}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <GripVertical className="w-4 h-4 text-gray-400 cursor-grab" />
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {formatDate(post.created_at)}
                          </span>
                        </div>

                        <div className="mb-2">
                          <p className="text-sm text-gray-900 dark:text-gray-100 line-clamp-3">
                            {getPostPreview(post)}
                          </p>
                        </div>

                        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
                          {post.hashtags && post.hashtags.length > 0 && (
                            <div className="flex items-center gap-1">
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                #{post.hashtags.length}
                              </span>
                            </div>
                          )}
                          {post.images && post.images.length > 0 && (
                            <div className="flex items-center gap-1">
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                Images: {post.images.length}
                              </span>
                            </div>
                          )}
                          {post.scheduled_time && (
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              {formatDate(post.scheduled_time)}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {columnPosts.length === 0 && (
                    <div className="flex items-center justify-center h-32 text-gray-400 dark:text-gray-600 text-sm">
                      No posts
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
