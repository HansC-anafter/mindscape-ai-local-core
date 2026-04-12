'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { Review, ReviewPanelProps } from './review/types';
import { buildReviewsFromArtifactsResponse } from './review/parseReviewArtifacts';
import { executeWorkspacePlaybook, fetchWorkspaceArtifacts } from './api';
import { ReviewDetailView } from './review/components/ReviewDetailView';
import { ReviewListView } from './review/components/ReviewListView';

export default function ReviewPanel({
  workspaceId,
  apiUrl
}: ReviewPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'approved' | 'rejected' | 'revised'>('all');

  useEffect(() => {
    loadReviews();
  }, [workspaceId, apiUrl]);

  const loadReviews = async () => {
    setLoading(true);
    try {
      const response = await fetchWorkspaceArtifacts(client, workspaceId, {
        platform: 'instagram',
        include_content: false,
        include_preview: false,
        limit: 100,
      });

      if (!response.ok) {
        throw new Error('Failed to load artifacts');
      }

      const data = await response.json();
      setReviews(buildReviewsFromArtifactsResponse(data));
    } catch (err) {
      console.error('Failed to load reviews:', err);
      setReviews([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddReviewNote = async (postPath: string, note: string, status: 'pending' | 'addressed' | 'resolved' | 'rejected') => {
    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_review_system',
        inputs: {
          action: 'add_review_note',
          workspace_id: workspaceId,
          post_path: postPath,
          reviewer: 'user', // TODO: Get actual reviewer from context
          note: note,
          status: status
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        await loadReviews();
        alert('Review note added');
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add review note');
      }
    } catch (err) {
      console.error('Failed to add review note:', err);
      alert(`Failed to add review note: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAddDecisionLog = async (postPath: string, decision: 'approve' | 'reject' | 'revise', rationale: string) => {
    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_review_system',
        inputs: {
          action: 'add_decision_log',
          workspace_id: workspaceId,
          post_path: postPath,
          decision: decision,
          rationale: rationale,
          decision_maker: 'user' // TODO: Get actual decision_maker from context
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        await loadReviews();
        alert('Decision log added');
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add decision log');
      }
    } catch (err) {
      console.error('Failed to add decision log:', err);
      alert(`Failed to add decision log: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAddChangelog = async (postPath: string, version: string, changes: string, author: string) => {
    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_review_system',
        inputs: {
          action: 'add_changelog',
          workspace_id: workspaceId,
          post_path: postPath,
          version: version,
          changes: changes,
          author: author
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        await loadReviews();
        alert('Changelog added');
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add changelog');
      }
    } catch (err) {
      console.error('Failed to add changelog:', err);
      alert(`Failed to add changelog: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateReviewStatus = async (postPath: string, noteIndex: number, newStatus: 'pending' | 'addressed' | 'resolved' | 'rejected') => {
    setLoading(true);
    try {
      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_review_system',
        inputs: {
          action: 'update_review_note_status',
          workspace_id: workspaceId,
          post_path: postPath,
          note_index: noteIndex,
          new_status: newStatus
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        await loadReviews();
        alert('Review status updated');
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to update review status');
      }
    } catch (err) {
      console.error('Failed to update review status:', err);
      alert(`Failed to update review status: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const filteredReviews = reviews.filter(review => {
    if (filterStatus === 'all') return true;
    return review.status === filterStatus;
  });

  if (selectedReview) {
    return (
      <ReviewDetailView
        review={selectedReview}
        loading={loading}
        onBack={() => setSelectedReview(null)}
        onAddReviewNote={handleAddReviewNote}
        onAddDecisionLog={handleAddDecisionLog}
        onAddChangelog={handleAddChangelog}
        onUpdateReviewNoteStatus={handleUpdateReviewStatus}
      />
    );
  }

  return (
    <ReviewListView
      reviews={filteredReviews}
      loading={loading}
      filterStatus={filterStatus}
      onFilterStatusChange={setFilterStatus}
      onSelectReview={setSelectedReview}
    />
  );
}
