/**
 * Habit Learning API Client
 * 提供習慣學習相關的 API 調用函數
 */

import { getApiBaseUrl } from './api-url';

const API_URL = getApiBaseUrl();

export interface HabitCandidate {
  id: string;
  profile_id: string;
  habit_key: string;
  habit_value: string;
  habit_category: string;
  evidence_count: number;
  confidence: number;
  first_seen_at?: string;
  last_seen_at?: string;
  evidence_refs: string[];
  status: 'pending' | 'confirmed' | 'rejected' | 'superseded';
  created_at: string;
  updated_at: string;
}

export interface HabitCandidateResponse {
  candidate: HabitCandidate;
  suggestion_message: string;
}

export interface HabitAuditLog {
  id: string;
  profile_id: string;
  candidate_id: string;
  action: string;
  previous_status?: string;
  new_status?: string;
  actor_type: string;
  actor_id?: string;
  reason?: string;
  metadata?: any;
  created_at: string;
}

export interface HabitMetrics {
  total_observations: number;
  total_candidates: number;
  pending_candidates: number;
  confirmed_candidates: number;
  rejected_candidates: number;
  acceptance_rate: number;
  candidate_hit_rate?: number;
  is_habit_suggestions_enabled?: boolean;
}

/**
 * 取得候選習慣列表
 */
export async function getCandidates(
  profileId: string,
  status?: 'pending' | 'confirmed' | 'rejected',
  limit: number = 50
): Promise<HabitCandidateResponse[]> {
  const params = new URLSearchParams({
    profile_id: profileId,
    limit: limit.toString(),
  });
  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`${API_URL}/api/v1/habits/candidates?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to get candidates: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 取得單個候選習慣
 */
export async function getCandidate(
  candidateId: string,
  profileId: string
): Promise<HabitCandidate> {
  const response = await fetch(
    `${API_URL}/api/v1/habits/candidates/${candidateId}?profile_id=${profileId}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get candidate: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 確認候選習慣
 */
export async function confirmCandidate(
  candidateId: string,
  profileId: string,
  reason?: string
): Promise<HabitCandidate> {
  const response = await fetch(
    `${API_URL}/api/v1/habits/candidates/${candidateId}/confirm?profile_id=${profileId}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to confirm candidate: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 拒絕候選習慣
 */
export async function rejectCandidate(
  candidateId: string,
  profileId: string,
  reason?: string
): Promise<HabitCandidate> {
  const response = await fetch(
    `${API_URL}/api/v1/habits/candidates/${candidateId}/reject?profile_id=${profileId}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to reject candidate: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 回滾候選習慣
 */
export async function rollbackCandidate(
  candidateId: string,
  profileId: string
): Promise<HabitCandidate> {
  const response = await fetch(
    `${API_URL}/api/v1/habits/candidates/${candidateId}/rollback?profile_id=${profileId}`,
    {
      method: 'POST',
    }
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || `Failed to rollback candidate: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 取得審計記錄
 */
export async function getAuditLogs(
  profileId: string,
  candidateId?: string,
  limit: number = 100
): Promise<HabitAuditLog[]> {
  const params = new URLSearchParams({
    profile_id: profileId,
    limit: limit.toString(),
  });
  if (candidateId) {
    params.append('candidate_id', candidateId);
  }

  const response = await fetch(`${API_URL}/api/v1/habits/audit-logs?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to get audit logs: ${response.statusText}`);
  }
  return response.json();
}

/**
 * 取得統計資訊
 */
export async function getMetrics(profileId: string): Promise<HabitMetrics> {
  const response = await fetch(
    `${API_URL}/api/v1/habits/metrics?profile_id=${profileId}`
  );
  if (!response.ok) {
    throw new Error(`Failed to get metrics: ${response.statusText}`);
  }
  return response.json();
}
