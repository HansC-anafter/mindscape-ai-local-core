/**
 * Shared types for WorkbenchExecutionPanel
 */
import type { IGPost, PostStatus } from '../../../types';

// ==================== Props Types ====================

export interface WorkbenchExecutionPanelProps {
    workspaceId: string;
    apiUrl: string;
    activeBrowserProfile: {
        profileName: string;
        profilePath: string;
        pathSource?: string;
        loggedIn: boolean;
        sessionExpired: boolean;
        isChecking: boolean;
        igUsername?: string | null;
        availableProfiles: Array<{
            name: string;
            logged_in: boolean;
            session_expired: boolean;
            ig_username: string | null;
        }>;
        onSelectProfile: (profileName: string) => void;
        onRefreshStatus: () => void;
        onOpenAccess: () => void;
    };
    selectedPostId: string | null;
    getSelectedPost: () => IGPost | null;
    posts: IGPost[];
    statusFilter: PostStatus | 'all';
    runLogCounts: RunLogCounts;
    targetsTotal: number | null;
    recentRuns: RunInfo[];
    recentGroups: any[];
    isRunning: boolean;
    error: string | null;
    onDismissError: () => void;
    onRunPlaybook: (playbookCode: string, additionalInputs?: any) => Promise<{ success: boolean; execution_id?: string; error?: string }>;
    onRefreshRuns?: () => void;
}

export interface RunLogCounts {
    total: number;
    completed: number;
    running: number;
    pending: number;
    failed: number;
}

// ==================== Run Types ====================

export interface RunInfo {
    id?: string;
    execution_id?: string;
    playbook_code?: string;
    status?: string;
    started_at?: string;
    created_at?: string;
    completed_at?: string;
    execution_context?: {
        inputs?: {
            target_username?: string;
            [key: string]: any;
        };
        target_username?: string;
        [key: string]: any;
    };
    task?: {
        created_at?: string;
        started_at?: string;
        error?: string;
    };
    [key: string]: any;
}

export interface QueueGroupSummary {
    parent_execution_id: string;
    latest_at?: string | null;
    summary: {
        total: number;
        completed: number;
        running: number;
        pending: number;
        failed: number;
    };
    representative_run: RunInfo;
}

export interface ForcedExecution {
    executionId: string;
    playbookCode: string;
    startedAt: string | null;
}

// ==================== IG Debug Types ====================

export interface IGDebugInfo {
    executionId: string;
    updatedAt: string | null;
    stage: string | null;
    iter: number | null;
    targets: number | null;
    expectedFollowing: number | null;
    stopReason: string | null;
    listCaptureStatus: string | null;
    executionBackendHint: string | null;
    visitAccountPages: boolean | null;
    savedDedupTargets: number | null;
    visitedCount: number | null;
    pageIndex: number | null;
    pageTotal: number | null;
    currentAccount: string | null;
    noChangeCount: number | null;
    noNewAccountsStreak: number | null;
    reachedBottom: boolean | null;
    errorType: string | null;
    errorMessage: string | null;
    scrollMode: string | null;
    runMode: string | null;
    allowPartialResume: boolean | null;
    sourceProfileRef: string | null;
    sourceAccountHandle: string | null;
    screenshots: string[];
    // Health diagnostics
    heartbeatAt: string | null;
    runnerId: string | null;
    heartbeatAgeSeconds: number | null;
    progressAgeSeconds: number | null;
    isZombie: boolean;
    streakRatio: number | null;
    riskCooldownUntil: string | null;
    riskReason: string | null;
    riskSignalTarget: string | null;
}

// ==================== Tab Types ====================

export type TabType = 'logs' | 'queue' | 'actions' | 'ready';

// ==================== Batch Processing Types ====================

export type BatchActionType = 'batch_validate' | 'batch_generate_export_packs' | 'batch_update_status' | 'batch_process';
export type BatchScopeType = 'selected' | 'filtered' | 'manual';
export type PostStatusType = 'draft' | 'review' | 'ready' | 'scheduled' | 'published' | 'measured' | 'archived';

// ==================== Workflow Types ====================

export type WorkflowPresetType = 'create_post_workflow' | 'review_workflow' | 'execute_workflow';

// ==================== Utility Types ====================

export interface ExecutionStartedEvent {
    workspaceId: string;
    executionId: string;
    playbookCode: string;
    startedAt?: string;
}
