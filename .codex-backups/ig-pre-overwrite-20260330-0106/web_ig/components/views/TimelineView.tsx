'use client';

/**
 * Timeline View
 *
 * Features:
 * - Timeline component implementation
 * - Schedule visualization
 * - Series progress display
 */

import React, { useState, useEffect } from 'react';
import { parseServerTimestamp } from '@/lib/time';
import { Calendar, Clock, CheckCircle2, PlayCircle, FileText } from 'lucide-react';
import type { IGPost } from '../types';

interface TimelineViewProps {
  posts: IGPost[];
  selectedPostId: string | null;
  onPostSelect: (postId: string) => void;
  statusFilter: string;
}

interface TimelineEvent {
  id: string;
  date: Date;
  type: 'post' | 'series' | 'schedule';
  title: string;
  description?: string;
  status: string;
  post?: IGPost;
}

export default function TimelineView({
  posts,
  selectedPostId,
  onPostSelect,
  statusFilter
}: TimelineViewProps) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [viewMode, setViewMode] = useState<'day' | 'week' | 'month'>('week');
  const [currentDate, setCurrentDate] = useState(new Date());

  useEffect(() => {
    buildTimelineEvents();
  }, [posts, statusFilter, viewMode, currentDate]);

  const buildTimelineEvents = () => {
    const filteredPosts = statusFilter === 'all'
      ? posts
      : posts.filter(p => p.status === statusFilter);

    const timelineEvents: TimelineEvent[] = filteredPosts
      .filter(post => {
        return post.scheduled_time || post.status === 'published';
      })
      .map(post => {
        const date = post.scheduled_time
          ? (parseServerTimestamp(post.scheduled_time) ?? new Date(post.scheduled_time))
          : post.status === 'published'
            ? (parseServerTimestamp(post.created_at) ?? new Date(post.created_at))
            : (parseServerTimestamp(post.created_at) ?? new Date(post.created_at));

        return {
          id: post.id,
          date,
          type: 'post' as const,
          title: post.text?.substring(0, 50) || post.artifact_id,
          description: post.text?.substring(0, 200) || undefined,
          status: post.status,
          post
        };
      })
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    setEvents(timelineEvents);
  };

  const formatDate = (date: Date): string => {
    const now = new Date();
    const diffTime = date.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    if (diffDays === -1) return 'Yesterday';
    if (diffDays > 0 && diffDays <= 7) return `In ${diffDays} day${diffDays > 1 ? 's' : ''}`;
    if (diffDays < 0 && diffDays >= -7) return `${Math.abs(diffDays)} day${Math.abs(diffDays) > 1 ? 's' : ''} ago`;

    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const toLocalDateKey = (date: Date): string => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };

  const fromLocalDateKey = (key: string): Date => {
    const [yy, mm, dd] = key.split('-').map((v) => Number.parseInt(v, 10));
    if (!Number.isFinite(yy) || !Number.isFinite(mm) || !Number.isFinite(dd)) return new Date();
    return new Date(yy, mm - 1, dd);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'published':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'scheduled':
        return <Clock className="w-4 h-4 text-blue-500" />;
      case 'ready':
        return <PlayCircle className="w-4 h-4 text-yellow-500" />;
      default:
        return <FileText className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'published':
        return 'bg-green-100 dark:bg-green-900/20 border-green-300 dark:border-green-700';
      case 'scheduled':
        return 'bg-blue-100 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700';
      case 'ready':
        return 'bg-yellow-100 dark:bg-yellow-900/20 border-yellow-300 dark:border-yellow-700';
      default:
        return 'bg-gray-100 dark:bg-gray-700 border-gray-300 dark:border-gray-600';
    }
  };

  const groupedEvents = events.reduce((acc, event) => {
    const dateKey = toLocalDateKey(event.date);
    if (!acc[dateKey]) {
      acc[dateKey] = [];
    }
    acc[dateKey].push(event);
    return acc;
  }, {} as Record<string, TimelineEvent[]>);

  const sortedDateKeys = Object.keys(groupedEvents).sort();

  const navigateDate = (direction: 'prev' | 'next') => {
    const newDate = new Date(currentDate);
    if (viewMode === 'day') {
      newDate.setDate(newDate.getDate() + (direction === 'next' ? 1 : -1));
    } else if (viewMode === 'week') {
      newDate.setDate(newDate.getDate() + (direction === 'next' ? 7 : -7));
    } else {
      newDate.setMonth(newDate.getMonth() + (direction === 'next' ? 1 : -1));
    }
    setCurrentDate(newDate);
  };

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigateDate('prev')}
            className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            {'<'}
          </button>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {currentDate.toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric'
            })}
          </span>
          <button
            onClick={() => navigateDate('next')}
            className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            {'>'}
          </button>
        </div>

        <div className="flex items-center gap-2">
          {(['day', 'week', 'month'] as const).map(mode => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${viewMode === mode
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
            >
              {mode === 'day' ? 'Day View' : mode === 'week' ? 'Week View' : 'Month View'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sortedDateKeys.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <Calendar className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-sm">No scheduled or published posts</p>
          </div>
        ) : (
          <div className="relative">
            <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gray-300 dark:bg-gray-600"></div>

            <div className="space-y-8">
              {sortedDateKeys.map((dateKey) => {
                const dateEvents = groupedEvents[dateKey];
                const date = fromLocalDateKey(dateKey);

                return (
                  <div key={dateKey} className="relative">
                    <div className="flex items-center gap-4 mb-4">
                      <div className="w-12 h-12 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold z-10 relative">
                        {date.getDate()}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {formatDate(date)}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          {date.toLocaleDateString('en-US', {
                            weekday: 'long'
                          })}
                        </div>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {dateEvents.length} event{dateEvents.length !== 1 ? 's' : ''}
                      </div>
                    </div>

                    <div className="ml-6 space-y-4">
                      {dateEvents.map((event) => (
                        <div
                          key={event.id}
                          onClick={() => event.post && onPostSelect(event.id)}
                          className={`p-4 rounded-lg border cursor-pointer transition-all hover:shadow-md ${selectedPostId === event.id
                              ? 'ring-2 ring-blue-500'
                              : ''
                            } ${getStatusColor(event.status)}`}
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              {getStatusIcon(event.status)}
                              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                {event.title}
                              </span>
                            </div>
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {formatTime(event.date)}
                            </span>
                          </div>
                          {event.description && (
                            <p className="text-xs text-gray-600 dark:text-gray-300 mt-2 line-clamp-2">
                              {event.description}
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-3">
                            <span className={`px-2 py-0.5 text-xs rounded ${event.status === 'published' ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200' :
                                event.status === 'scheduled' ? 'bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200' :
                                  event.status === 'ready' ? 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200' :
                                    'bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-300'
                              }`}>
                              {event.status === 'published' ? 'Published' :
                                event.status === 'scheduled' ? 'Scheduled' :
                                  event.status === 'ready' ? 'Ready' :
                                    event.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
