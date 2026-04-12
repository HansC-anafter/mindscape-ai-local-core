import React from 'react';
import { formatLocalDateTime } from '@/lib/time';

import type { Review } from '../types';

export function ReviewListView(props: {
  reviews: Review[];
  loading: boolean;
  filterStatus: 'all' | 'pending' | 'approved' | 'rejected' | 'revised';
  onFilterStatusChange: (value: 'all' | 'pending' | 'approved' | 'rejected' | 'revised') => void;
  onSelectReview: (review: Review) => void;
}) {
  const { reviews, loading, filterStatus, onFilterStatusChange, onSelectReview } = props;

  return (
    <div className="h-full flex flex-col p-4">
      <div className="mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          Review System
        </h2>

        <div className="flex items-center gap-2 flex-wrap mb-4">
          {(['all', 'pending', 'approved', 'rejected', 'revised'] as const).map((status) => (
            <button
              key={status}
              onClick={() => onFilterStatusChange(status)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${filterStatus === status
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
            >
              {status === 'all' ? 'All' :
                status === 'pending' ? 'Pending' :
                  status === 'approved' ? 'Approved' :
                    status === 'rejected' ? 'Rejected' :
                      'Revised'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            Loading reviews...
          </div>
        ) : reviews.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            No review records
          </div>
        ) : (
          reviews.map((review, index) => (
            <div
              key={index}
              onClick={() => onSelectReview(review)}
              className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 cursor-pointer transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
                    {review.post_path}
                  </h3>
                  {review.review_notes && review.review_notes.length > 0 && (
                    <p className="text-xs text-gray-600 dark:text-gray-300 truncate">
                      {review.review_notes.length} note{review.review_notes.length !== 1 ? 's' : ''}
                      {review.review_notes.filter((n) => n.status === 'pending').length > 0 && (
                        <span className="ml-1 text-red-600 dark:text-red-400">
                          ({review.review_notes.filter((n) => n.status === 'pending').length} pending)
                        </span>
                      )}
                    </p>
                  )}
                </div>
                <span className={`px-2 py-1 text-xs rounded ${review.status === 'approved' ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' :
                    review.status === 'rejected' ? 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' :
                      review.status === 'revised' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400' :
                        'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                  }`}>
                  {review.status === 'approved' ? 'Approved' :
                    review.status === 'rejected' ? 'Rejected' :
                      review.status === 'revised' ? 'Revised' :
                        'Pending'}
                </span>
              </div>
              {review.reviewed_at && (
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  {formatLocalDateTime(review.reviewed_at)}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

