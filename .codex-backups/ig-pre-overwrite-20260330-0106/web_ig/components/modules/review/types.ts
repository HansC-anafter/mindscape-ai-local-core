export interface ReviewPanelProps {
  workspaceId: string;
  apiUrl: string;
}

export interface ReviewNote {
  reviewer: string;
  note: string;
  priority?: string;
  status: 'pending' | 'addressed' | 'resolved' | 'rejected';
  timestamp?: string;
  updated_at?: string;
}

export interface Review {
  post_path: string;
  status: 'pending' | 'approved' | 'rejected' | 'revised';
  review_notes?: ReviewNote[];
  reviewer?: string;
  reviewed_at?: string;
  changelog?: Array<{
    timestamp: string;
    field: string;
    old_value: unknown;
    new_value: unknown;
  }>;
  decision_log?: Array<{
    timestamp: string;
    decision: 'approve' | 'reject' | 'revise';
    reason?: string;
    reviewer?: string;
  }>;
}

