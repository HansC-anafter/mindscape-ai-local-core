import type { MeetingCommandLedgerAcceptance } from '@/components/capabilities/meeting-workbench/meetingCommandLedger';

export type MotionPracticeSessionRollupSummary = {
  window_count?: number;
  duration_ms?: number;
  confidence_stats?: Record<string, number>;
  score_summary?: Record<string, number>;
  finding_counts?: Record<string, number>;
  top_findings?: string[];
  motion_window_refs?: string[];
  motion_window_digests?: Record<string, unknown>[];
  [key: string]: unknown;
};

export type MotionPracticeSessionRollupResponse = {
  emitted?: boolean;
  live_session_id?: string;
  motion_rollup_ref?: string;
  artifact_id?: string;
  artifact_registry?: Record<string, unknown>;
  summary?: MotionPracticeSessionRollupSummary;
  [key: string]: unknown;
};

export type MotionPracticeClosureResult = {
  rollup: MotionPracticeSessionRollupResponse;
  command: MeetingCommandLedgerAcceptance;
};
