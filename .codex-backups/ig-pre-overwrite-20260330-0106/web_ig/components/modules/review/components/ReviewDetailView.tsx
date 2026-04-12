import React from 'react';

import type { Review } from '../types';

export function ReviewDetailView(props: {
  review: Review;
  loading: boolean;
  onBack: () => void;
  onAddReviewNote: (postPath: string, note: string, status: 'pending' | 'addressed' | 'resolved' | 'rejected') => void;
  onAddDecisionLog: (postPath: string, decision: 'approve' | 'reject' | 'revise', rationale: string) => void;
  onAddChangelog: (postPath: string, version: string, changes: string, author: string) => void;
  onUpdateReviewNoteStatus: (postPath: string, noteIndex: number, newStatus: 'pending' | 'addressed' | 'resolved' | 'rejected') => void;
}) {
  const { review, loading, onBack, onAddReviewNote, onAddDecisionLog, onAddChangelog, onUpdateReviewNoteStatus } = props;

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={onBack}
          className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        >
          Back to Review List
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Review Details
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {review.post_path}
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Status
            </span>
            <span className={`px-2 py-1 text-xs rounded ${
              review.status === 'approved' ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' :
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
          {review.reviewer && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Reviewer: {review.reviewer}
            </p>
          )}
          {review.reviewed_at && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Reviewed at: {new Date(review.reviewed_at).toLocaleString()}
            </p>
          )}
        </div>

        {review.review_notes && review.review_notes.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Review Notes ({review.review_notes.length})
            </h3>
            <div className="space-y-3">
              {review.review_notes.map((note, index) => (
                <div key={index} className="border-l-2 border-blue-300 dark:border-blue-600 pl-3 py-2">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                          {note.reviewer || 'Unknown Reviewer'}
                        </span>
                        {note.priority && (
                          <span className={`px-1.5 py-0.5 text-xs rounded ${
                            note.priority === 'high' ? 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' :
                            note.priority === 'medium' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400' :
                            'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                          }`}>
                            {note.priority === 'high' ? 'High' : note.priority === 'medium' ? 'Medium' : 'Low'}
                          </span>
                        )}
                        <span className={`px-1.5 py-0.5 text-xs rounded ${
                          note.status === 'resolved' ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' :
                          note.status === 'addressed' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' :
                          note.status === 'rejected' ? 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' :
                          'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                        }`}>
                          {note.status === 'resolved' ? 'Resolved' :
                           note.status === 'addressed' ? 'Addressed' :
                           note.status === 'rejected' ? 'Rejected' :
                           'Pending'}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
                        {note.note}
                      </p>
                      {note.timestamp && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          {new Date(note.timestamp).toLocaleString()}
                        </div>
                      )}
                    </div>
                    <div className="ml-2 flex flex-col gap-1">
                      <select
                        value={note.status}
                        onChange={(e) => {
                          onUpdateReviewNoteStatus(
                            review.post_path,
                            index,
                            e.target.value as 'pending' | 'addressed' | 'resolved' | 'rejected'
                          );
                        }}
                        disabled={loading}
                        className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 disabled:opacity-50"
                      >
                        <option value="pending">Pending</option>
                        <option value="addressed">Addressed</option>
                        <option value="resolved">Resolved</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {review.changelog && review.changelog.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Changelog
            </h3>
            <div className="space-y-2">
              {review.changelog.map((change, index) => (
                <div key={index} className="text-xs border-l-2 border-gray-300 dark:border-gray-600 pl-3">
                  <div className="text-gray-500 dark:text-gray-400">
                    {new Date(change.timestamp).toLocaleString()}
                  </div>
                  <div className="text-gray-700 dark:text-gray-300 mt-1">
                    <span className="font-medium">{change.field}</span>:
                    <span className="text-red-600 dark:text-red-400 line-through ml-1">{JSON.stringify(change.old_value)}</span>
                    {' -> '}
                    <span className="text-green-600 dark:text-green-400">{JSON.stringify(change.new_value)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {review.decision_log && review.decision_log.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Decision Log
            </h3>
            <div className="space-y-2">
              {review.decision_log.map((decision, index) => (
                <div key={index} className="text-xs border-l-2 border-blue-300 dark:border-blue-600 pl-3">
                  <div className="text-gray-500 dark:text-gray-400">
                    {new Date(decision.timestamp).toLocaleString()}
                  </div>
                  <div className="text-gray-700 dark:text-gray-300 mt-1">
                    <span className={`font-medium ${
                      decision.decision === 'approve' ? 'text-green-600 dark:text-green-400' :
                      decision.decision === 'reject' ? 'text-red-600 dark:text-red-400' :
                      'text-yellow-600 dark:text-yellow-400'
                    }`}>
                      {decision.decision === 'approve' ? 'Approve' :
                       decision.decision === 'reject' ? 'Reject' :
                       'Revise'}
                    </span>
                    {decision.reason && (
                      <span className="ml-2 text-gray-600 dark:text-gray-400">
                        - {decision.reason}
                      </span>
                    )}
                  </div>
                  {decision.reviewer && (
                    <div className="text-gray-500 dark:text-gray-400 mt-1">
                      Reviewer: {decision.reviewer}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Actions
          </h3>
          <div className="space-y-2">
            <button
              onClick={() => {
                const note = prompt('Enter review note:');
                if (note) {
                  const status = prompt('Status (pending/addressed/resolved/rejected, default pending):') || 'pending';
                  onAddReviewNote(review.post_path, note, status as 'pending' | 'addressed' | 'resolved' | 'rejected');
                }
              }}
              disabled={loading}
              className="w-full px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Add Review Note
            </button>

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => {
                  const rationale = prompt('Enter approval rationale:') || 'Approved';
                  onAddDecisionLog(review.post_path, 'approve', rationale);
                }}
                disabled={loading}
                className="px-3 py-2 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                onClick={() => {
                  const rationale = prompt('Enter rejection rationale:') || 'Rejected';
                  onAddDecisionLog(review.post_path, 'reject', rationale);
                }}
                disabled={loading}
                className="px-3 py-2 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                Reject
              </button>
              <button
                onClick={() => {
                  const rationale = prompt('Enter revision requirements:') || 'Revised';
                  onAddDecisionLog(review.post_path, 'revise', rationale);
                }}
                disabled={loading}
                className="px-3 py-2 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
              >
                Revise
              </button>
            </div>

            <button
              onClick={() => {
                const version = prompt('Version:') || '1.0';
                const changes = prompt('Changes:');
                const author = prompt('Author:') || 'user';
                if (changes) {
                  onAddChangelog(review.post_path, version, changes, author);
                }
              }}
              disabled={loading}
              className="w-full px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
            >
              Add Changelog
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

