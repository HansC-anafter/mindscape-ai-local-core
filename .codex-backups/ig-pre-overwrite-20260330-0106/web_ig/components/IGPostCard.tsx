'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import { parseServerTimestamp } from '@/lib/time';
import type { IGPost } from './types';

interface IGPostCardProps {
  post: IGPost;
  onClick?: () => void;
}

export default function IGPostCard({ post, onClick }: IGPostCardProps) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [imageLoadFailed, setImageLoadFailed] = useState(false);
  const images = post.images || [];
  const fallbackImageDataUri =
    'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="400"%3E%3Crect fill="%23ddd" width="400" height="400"/%3E%3Ctext fill="%23999" font-family="sans-serif" font-size="18" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3EImage not found%3C/text%3E%3C/svg%3E';

  const apiUrl = getApiBaseUrl();

  const getProxiedImageUrl = (rawUrl?: string): string | undefined => {
    if (!rawUrl || typeof rawUrl !== 'string') return undefined;
    if (rawUrl.startsWith('data:') || rawUrl.startsWith('blob:')) return rawUrl;
    if (rawUrl.startsWith('/')) return rawUrl;
    try {
      const parsed = new URL(rawUrl);
      const host = (parsed.hostname || '').toLowerCase();
      if (
        host.endsWith('.fbcdn.net') ||
        host.endsWith('.cdninstagram.com') ||
        host === 'cdninstagram.com' ||
        host.endsWith('.instagram.com') ||
        host === 'instagram.com'
      ) {
        return `/api/v1/media/image?url=${encodeURIComponent(rawUrl)}`;
      }
    } catch {
      // ignore
    }
    return rawUrl;
  };

  const currentImageUrl = getProxiedImageUrl(images[currentImageIndex]);
  useEffect(() => {
    setImageLoadFailed(false);
  }, [currentImageUrl, currentImageIndex]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'published':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400';
      case 'scheduled':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400';
      case 'draft':
        return 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300';
      case 'archived':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400';
      default:
        return 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300';
    }
  };

  const formatDate = (dateString: string) => {
    const date = parseServerTimestamp(dateString) ?? new Date(dateString);
    return date.toLocaleDateString('zh-TW', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const previewText = post.text.length > 150 ? post.text.substring(0, 150) + '...' : post.text;

  return (
    <div
      onClick={onClick}
      className={`bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-lg transition-shadow p-4 cursor-pointer border border-gray-200 dark:border-gray-700 ${onClick ? 'hover:border-accent dark:hover:border-blue-500' : ''
        }`}
    >
      {/* Status badge */}
      <div className="flex items-center justify-between mb-2">
        <span
          className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(post.status)}`}
        >
          {post.status}
        </span>
        {post.scheduled_time && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {formatDate(post.scheduled_time)}
          </span>
        )}
      </div>

      {/* Images carousel - Always show, with placeholder if no images */}
      <div className="mb-3 relative">
        <div className="relative w-full aspect-square bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden">
          {images.length > 0 ? (
            <img
              src={imageLoadFailed ? fallbackImageDataUri : currentImageUrl}
              alt={`Post image ${currentImageIndex + 1}`}
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

          {/* Navigation arrows - Only show if there are multiple images */}
          {images.length > 1 && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentImageIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1));
                }}
                className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1.5 transition-colors"
                aria-label="Previous image"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setCurrentImageIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1));
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-1.5 transition-colors"
                aria-label="Next image"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </>
          )}

          {/* Image indicators - Only show if there are multiple images */}
          {images.length > 1 && (
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
              {images.map((_, index) => (
                <button
                  key={index}
                  onClick={(e) => {
                    e.stopPropagation();
                    setCurrentImageIndex(index);
                  }}
                  className={`h-1.5 rounded-full transition-all ${index === currentImageIndex
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

      {/* Post text preview */}
      <div className="mb-3">
        <p className="text-sm text-gray-800 dark:text-gray-200 line-clamp-4">
          {previewText}
        </p>
      </div>

      {/* Hashtags */}
      {post.hashtags && post.hashtags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {post.hashtags.slice(0, 3).map((tag, index) => (
            <span
              key={index}
              className="text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded"
            >
              #{tag}
            </span>
          ))}
          {post.hashtags.length > 3 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              +{post.hashtags.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Metadata */}
      <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{formatDate(post.created_at)}</span>
        {post.platform && (
          <span className="capitalize">{post.platform}</span>
        )}
      </div>
    </div>
  );
}
