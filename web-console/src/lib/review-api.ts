/**
 * Review Suggestion API Client
 * 提供回顧建議相關的 API 調用函數
 */

import { getApiBaseUrl } from './api-url';

const API_URL = getApiBaseUrl();

export interface ReviewSuggestion {
  since: string;
  until: string;
  total_entries: number;
  insight_events: number;
}

export interface ReviewSuggestionResponse {
  suggestion: ReviewSuggestion | null;
}

export interface ReviewPreferences {
  cadence: 'manual' | 'weekly' | 'monthly';
  day_of_week: number; // 0=Mon ... 6=Sun
  day_of_month: number; // 1-31
  time_of_day: string; // e.g., "21:00"
  min_entries: number;
  min_insight_events: number;
}

/**
 * 取得回顧建議
 */
export async function getReviewSuggestion(
  profileId: string
): Promise<ReviewSuggestion | null> {
  const response = await fetch(
    `${API_URL}/api/v1/review/suggestion?profile_id=${profileId}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get review suggestion: ${response.statusText}`);
  }
  const data: ReviewSuggestionResponse = await response.json();
  return data.suggestion;
}

/**
 * 記錄回顧已完成
 */
export async function recordReviewCompleted(
  profileId: string,
  reviewTime?: string
): Promise<void> {
  const params = new URLSearchParams({
    profile_id: profileId,
  });
  if (reviewTime) {
    params.append('review_time', reviewTime);
  }

  const response = await fetch(
    `${API_URL}/api/v1/review/completed?${params}`,
    {
      method: 'POST',
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to record review completion: ${response.statusText}`);
  }
}
