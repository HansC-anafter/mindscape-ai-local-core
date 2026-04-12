'use client';

import React from 'react';
import IGPostCard from './IGPostCard';
import type { IGPost, PostStatus } from './types';

interface IGGridViewProps {
  posts: IGPost[];
  selectedPostId?: string | null;
  onPostSelect?: (postId: string) => void;
  statusFilter?: PostStatus | 'all';
  onRefresh?: () => void;
}

export default function IGGridView({
  posts,
  selectedPostId,
  onPostSelect,
  statusFilter = 'all',
  onRefresh
}: IGGridViewProps) {
  const filteredPosts = React.useMemo(() => {
    if (statusFilter === 'all') {
      return posts;
    }
    return posts.filter(post => {
      const status = post.status || 'draft';
      return status === statusFilter;
    });
  }, [posts, statusFilter]);

  const handlePostClick = (postId: string) => {
    if (onPostSelect) {
      onPostSelect(postId);
    }
  };

  if (filteredPosts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500 dark:text-gray-400">
          <p className="text-lg mb-2">No posts found</p>
          {statusFilter !== 'all' && (
            <p className="text-sm">No posts with status: {statusFilter}</p>
          )}
          {statusFilter === 'all' && (
            <p className="text-sm">Create your first Instagram post to get started</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 overflow-y-auto h-full">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredPosts.map((post) => (
          <div
            key={post.id}
            onClick={() => handlePostClick(post.id)}
            className={`
              cursor-pointer transition-all
              ${selectedPostId === post.id
                ? 'ring-2 ring-blue-500 dark:ring-blue-400 ring-offset-2 rounded-lg'
                : 'hover:ring-1 hover:ring-gray-300 dark:hover:ring-gray-600 rounded-lg'
              }
            `}
          >
            <IGPostCard post={post} />
          </div>
        ))}
      </div>
    </div>
  );
}

