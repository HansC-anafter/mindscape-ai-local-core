'use client';

import React, { useEffect, useState } from 'react';
import { parseServerTimestamp } from '@/lib/time';
import type { IGPost } from './types';

interface IGTimelineViewProps {
  posts: IGPost[];
  onSchedule: (postId: string, scheduledTime: string) => void;
}

function ImageCarousel({ images }: { images: string[] }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [imageLoadFailed, setImageLoadFailed] = useState(false);
  const fallbackImageDataUri =
    'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="400"%3E%3Crect fill="%23ddd" width="400" height="400"/%3E%3Ctext fill="%23999" font-family="sans-serif" font-size="18" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3EImage not found%3C/text%3E%3C/svg%3E';

  const currentImageSrc = images[currentIndex];
  useEffect(() => {
    setImageLoadFailed(false);
  }, [currentImageSrc, currentIndex]);

  return (
    <div className="relative mb-3">
      <div className="relative w-full aspect-square bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden">
        {images.length > 0 ? (
          <img
            src={imageLoadFailed ? fallbackImageDataUri : currentImageSrc}
            alt={`Post image ${currentIndex + 1}`}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setImageLoadFailed(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg className="w-16 h-16 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
        )}

        {/* Navigation arrows */}
        {images.length > 1 && (
          <>
            <button
              onClick={() => setCurrentIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1))}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1.5 transition-colors"
              aria-label="Previous image"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={() => setCurrentIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1))}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1.5 transition-colors"
              aria-label="Next image"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </>
        )}

        {/* Image indicators */}
        {images.length > 1 && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
            {images.map((_, index) => (
              <button
                key={index}
                onClick={() => setCurrentIndex(index)}
                className={`h-1.5 rounded-full transition-all ${index === currentIndex
                    ? 'bg-white w-6'
                    : 'bg-white/50 w-1.5 hover:bg-white/70'
                  }`}
                aria-label={`Go to image ${index + 1}`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function IGTimelineView({ posts, onSchedule }: IGTimelineViewProps) {
  const [selectedPost, setSelectedPost] = useState<IGPost | null>(null);
  const [scheduledTime, setScheduledTime] = useState('');

  const handleSchedule = () => {
    if (selectedPost && scheduledTime) {
      onSchedule(selectedPost.id, scheduledTime);
      setSelectedPost(null);
      setScheduledTime('');
    }
  };

  const formatDate = (dateString: string) => {
    const date = parseServerTimestamp(dateString) ?? new Date(dateString);
    return date.toLocaleDateString('zh-TW', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const sortedPosts = [...posts].sort((a, b) => {
    const dateA = a.scheduled_time ? (parseServerTimestamp(a.scheduled_time) ?? new Date(a.scheduled_time)).getTime() : 0;
    const dateB = b.scheduled_time ? (parseServerTimestamp(b.scheduled_time) ?? new Date(b.scheduled_time)).getTime() : 0;
    return dateB - dateA;
  });

  if (posts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500 dark:text-gray-400">
          <p className="text-lg mb-2">No posts found</p>
          <p className="text-sm">Create your first Instagram post to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 overflow-y-auto h-full">
      {/* Schedule dialog */}
      {selectedPost && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-4 dark:text-gray-100">
              Schedule Post
            </h3>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2 dark:text-gray-300">
                Scheduled Time
              </label>
              <input
                type="datetime-local"
                value={scheduledTime}
                onChange={(e) => setScheduledTime(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-gray-100"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setSelectedPost(null);
                  setScheduledTime('');
                }}
                className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleSchedule}
                disabled={!scheduledTime}
                className="px-4 py-2 bg-accent dark:bg-blue-600 text-white rounded-lg hover:opacity-80 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="space-y-4">
        {sortedPosts.map((post) => (
          <div
            key={post.id}
            className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 border border-gray-200 dark:border-gray-700"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${post.status === 'published'
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        : post.status === 'scheduled'
                          ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
                      }`}
                  >
                    {post.status}
                  </span>
                  {post.scheduled_time && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {formatDate(post.scheduled_time)}
                    </span>
                  )}
                </div>
                <ImageCarousel images={post.images || []} />
                <p className="text-sm text-gray-800 dark:text-gray-200 mb-2">
                  {post.text}
                </p>
                {post.hashtags && post.hashtags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2">
                    {post.hashtags.map((tag, index) => (
                      <span
                        key={index}
                        className="text-xs text-blue-600 dark:text-blue-400"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Created: {formatDate(post.created_at)}
                </div>
              </div>
              {post.status === 'draft' && (
                <button
                  onClick={() => setSelectedPost(post)}
                  className="ml-4 px-3 py-1 bg-accent dark:bg-blue-600 text-white text-sm rounded hover:opacity-80"
                >
                  Schedule
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
