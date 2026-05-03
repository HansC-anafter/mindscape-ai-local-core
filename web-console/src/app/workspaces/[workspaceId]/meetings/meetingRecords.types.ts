export interface MeetingSession {
    id: string;
    workspace_id: string;
    project_id?: string;
    thread_id?: string;
    started_at: string;
    ended_at?: string | null;
    is_active: boolean;
    status: string;
    meeting_type: string;
    agenda: string[];
    success_criteria: string[];
    round_count: number;
    max_rounds: number;
    action_items: ActionItem[];
    decisions: string[];
    minutes_md: string;
    metadata: Record<string, any>;
}

export interface CanonicalMemoryLink {
    memory_item_id: string;
    digest_id?: string;
    writeback_run_id?: string;
    lifecycle_status?: string;
    verification_status?: string;
}

export interface WorkflowEvidenceDiagnostics {
    profile?: string;
    scope?: string;
    section_order?: string[];
    section_limits?: Record<string, number>;
    total_candidate_count?: number;
    total_dropped_count?: number;
    candidate_counts?: Record<string, number>;
    selected_counts?: Record<string, number>;
    dropped_counts?: Record<string, number>;
    total_line_budget?: number;
    selected_line_count?: number;
    budget_utilization_ratio?: number;
    rendered?: boolean;
    rendered_section_count?: number;
}

export interface ActionItem {
    description?: string;
    status?: string;
    assignee?: string;
    [key: string]: any;
}
