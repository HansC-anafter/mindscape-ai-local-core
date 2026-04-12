import type { Review, ReviewNote } from './types';

function normalizeReviewNotes(value: unknown, fallbackReviewer: string): ReviewNote[] {
  if (Array.isArray(value)) return value as ReviewNote[];
  if (typeof value === 'string' && value.trim()) {
    return [{ reviewer: fallbackReviewer || 'unknown', note: value, status: 'pending' }];
  }
  if (value && typeof value === 'object') {
    return [value as ReviewNote];
  }
  return [];
}

export function buildReviewsFromArtifactsResponse(data: any): Review[] {
  const reviews: Review[] = [];

  (data?.artifacts || []).forEach((artifact: any) => {
    const metadata = artifact?.metadata || {};
    const frontmatter = metadata?.frontmatter || {};

    const hasReviewInfo =
      metadata.review_status ||
      frontmatter.review_status ||
      metadata.review_notes ||
      frontmatter.review_notes ||
      metadata.changelog ||
      frontmatter.changelog ||
      metadata.decision_log ||
      frontmatter.decision_log ||
      metadata.status === 'review';

    if (!hasReviewInfo) return;

    const reviewer = metadata.reviewer || frontmatter.reviewer;
    const reviewNotes = metadata.review_notes || frontmatter.review_notes;
    const reviewNotesArray = normalizeReviewNotes(reviewNotes, reviewer || 'unknown');

    reviews.push({
      post_path: metadata.post_path || artifact.storage_path || artifact.id,
      status: (metadata.review_status ||
        frontmatter.review_status ||
        (metadata.status === 'review' ? 'pending' : 'approved')) as Review['status'],
      review_notes: reviewNotesArray,
      reviewer,
      reviewed_at: metadata.reviewed_at || frontmatter.reviewed_at,
      changelog: metadata.changelog || frontmatter.changelog,
      decision_log: metadata.decision_log || frontmatter.decision_log,
    });
  });

  return reviews;
}

