/**
 * WorkbenchExecutionPanel - Modular Main Entry Point
 *
 * This is the refactored version of the execution panel,
 * organized into separate hooks, utils, types, and components.
 */
import React, { useState, useMemo, useCallback } from 'react';
import { AlertCircle, History, List, Sparkles, Activity, RefreshCw, Settings2, X } from 'lucide-react';

// Types
import type { WorkbenchExecutionPanelProps, BatchActionType, BatchScopeType, PostStatusType, WorkflowPresetType, RunInfo } from './types';

// Hooks
import { useExecutionState, useExecutionActions } from './hooks';

// Components
import { ActiveExecutionCard, ActionsTab, QueueTab, RunLogStatsCards } from './components';
import { getRunExecutionId, getRunInputs, getRunPrimarySubject, sortRuns } from './utils';

// External components
import ReadyScore from '../../../ReadyScore';

const ACTIVE_BROWSER_RUN_STATUSES = new Set(['running', 'queued', 'pending', 'paused']);

function normalizeProfilePath(value: unknown): string {
    return (value || '').toString().trim().replace(/\/+$/, '');
}

function humanizePlaybookCode(playbookCode: unknown): string {
    return (playbookCode || '')
        .toString()
        .trim()
        .replace(/^ig_/, '')
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ') || 'IG Run';
}

function describeRunForProfileState(run: RunInfo | null): string {
    if (!run) return '';
    const subject = getRunPrimarySubject(run);
    const base = humanizePlaybookCode(run.playbook_code);
    return subject ? `${base} · ${subject.value}` : base;
}

function matchesActiveProfile(run: RunInfo, normalizedProfilePath: string): boolean {
    if (!normalizedProfilePath) return false;

    const inputs = getRunInputs(run);
    const runProfilePath = normalizeProfilePath(inputs.user_data_dir);
    if (runProfilePath && runProfilePath === normalizedProfilePath) {
        return true;
    }

    const igLockKey = `ig_profile:${normalizedProfilePath}`;
    const explicitLockKey = `concurrency:user_data_dir:${normalizedProfilePath}`;
    const playbookCode = (run?.playbook_code || run?.execution_context?.playbook_code || '').toString().trim();
    const playbookInputLockKey = playbookCode
        ? `concurrency:playbook_input:${playbookCode}:${normalizedProfilePath}`
        : '';
    const candidateLockKeys = [
        run?.execution_context?.runner_skip_lock_key,
        run?.execution_context?.runner_lock_key,
        run?.execution_context?.runner_skip_conflict_lock_key,
    ]
        .map((value) => (value || '').toString().trim())
        .filter(Boolean);

    return (
        candidateLockKeys.includes(igLockKey) ||
        candidateLockKeys.includes(explicitLockKey) ||
        (!!playbookInputLockKey && candidateLockKeys.includes(playbookInputLockKey))
    );
}

export function WorkbenchExecutionPanel(props: WorkbenchExecutionPanelProps) {
    const {
        workspaceId,
        apiUrl,
        activeBrowserProfile,
        selectedPostId,
        getSelectedPost,
        posts,
        statusFilter,
        runLogCounts,
        targetsTotal,
        recentRuns,
        isRunning,
        error,
        onDismissError,
        onRunPlaybook,
        onRefreshRuns,
    } = props;

    // === State from hooks ===
    const {
        activeTab,
        setActiveTab,
        setForcedExecution,
    } = useExecutionState({ recentRuns, workspaceId, apiUrl, onRefreshRuns });

    const allIgRuns = useMemo(() => {
        const mergedRuns = Array.isArray(recentRuns) ? recentRuns : [];

        const deduped = new Map<string, RunInfo>();
        for (const run of mergedRuns) {
            const playbookCode = (run?.playbook_code || '').toString().trim();
            const executionId = getRunExecutionId(run);
            if (!playbookCode.startsWith('ig_')) continue;
            if (!executionId) continue;
            deduped.set(executionId, run);
        }

        return sortRuns(Array.from(deduped.values()));
    }, [recentRuns]);

    // Top debug cards should reflect every currently running IG task,
    // including grouped child tasks under batch parents.
    const runningIgRuns = useMemo(
        () =>
            allIgRuns.filter((run) => (run?.status || '').toString().toLowerCase() === 'running'),
        [allIgRuns],
    );

    const {
        rerunBusyId,
        rerunNotice,
        rerunNeedsTarget,
        rerunTargetInput,
        setRerunTargetInput,
        setRerunNeedsTarget,
        rerunExecution,
        cancelBusyId,
        cancelNotice,
        cancelExecution,
        canRerunStatus,
    } = useExecutionActions({
        apiUrl,
        workspaceId,
        onRefreshRuns,
        setActiveTab,
        setForcedExecution,
    });

    // === Batch Processor State ===
    const [batchAction, setBatchAction] = useState<BatchActionType>('batch_validate');
    const [batchScope, setBatchScope] = useState<BatchScopeType>('filtered');
    const [batchManualPostPaths, setBatchManualPostPaths] = useState('');
    const [batchStrictMode, setBatchStrictMode] = useState(false);
    const [igRerunAllowPartial, setIgRerunAllowPartial] = useState(false);
    const [batchOutputFolder, setBatchOutputFolder] = useState('export_packs');
    const [batchNewStatus, setBatchNewStatus] = useState<PostStatusType>('review');
    const [batchOperationsText, setBatchOperationsText] = useState('validate\nexport_pack');
    const [batchOperationConfigText, setBatchOperationConfigText] = useState('{}');
    const [batchNotice, setBatchNotice] = useState<string | null>(null);

    // === Workflow State ===
    const [workflowPreset, setWorkflowPreset] = useState<WorkflowPresetType>('create_post_workflow');
    const [workflowTargetFolder, setWorkflowTargetFolder] = useState('posts');
    const [workflowPostContent, setWorkflowPostContent] = useState('');
    const [workflowPostMetadataText, setWorkflowPostMetadataText] = useState('{}');
    const [workflowStepsText, setWorkflowStepsText] = useState('[]');
    const [workflowInitialContextText, setWorkflowInitialContextText] = useState('{}');
    const [workflowReviewNotesText, setWorkflowReviewNotesText] = useState('[]');
    const [workflowNotice, setWorkflowNotice] = useState<string | null>(null);

    // === Derived values ===
    const filteredPostPaths = useMemo(() => {
        const list = statusFilter === 'all' ? posts : posts.filter((p) => p.status === statusFilter);
        return list
            .map((p) => (p.post_path || '').toString().trim())
            .filter((p) => p.length > 0);
    }, [posts, statusFilter]);

    const activeProfileState = useMemo(() => {
        const normalizedProfilePath = normalizeProfilePath(activeBrowserProfile.profilePath);
        const matchingRuns = allIgRuns.filter((run) => {
            const status = (run?.status || '').toString().toLowerCase();
            if (!ACTIVE_BROWSER_RUN_STATUSES.has(status)) return false;
            return matchesActiveProfile(run, normalizedProfilePath);
        });
        const runningRuns = sortRuns(
            matchingRuns.filter((run) => (run?.status || '').toString().toLowerCase() === 'running')
        );
        const waitingRuns = sortRuns(
            matchingRuns.filter((run) => (run?.status || '').toString().toLowerCase() !== 'running')
        );
        const blockingRun = runningRuns[0] || null;
        const blockingLabel = describeRunForProfileState(blockingRun);

        if (!normalizedProfilePath) {
            return {
                label: 'Unknown',
                toneClass: 'text-gray-500 dark:text-gray-400',
                detail: 'Profile path is not available yet.',
            };
        }

        if (blockingRun) {
            const waitSuffix = waitingRuns.length > 0
                ? ` ${waitingRuns.length} queued.`
                : ' Some same-type browser runs may queue.';
            return {
                label: 'In use',
                toneClass: 'text-amber-600 dark:text-amber-400',
                detail: `Active: ${blockingLabel || 'another browser run'}.${waitSuffix}`,
            };
        }

        if (waitingRuns.length > 0) {
            return {
                label: 'Queueing',
                toneClass: 'text-blue-600 dark:text-blue-400',
                detail: `${waitingRuns.length} same-profile run${waitingRuns.length === 1 ? '' : 's'} waiting for this profile.`,
            };
        }

        return {
            label: 'Available',
            toneClass: 'text-emerald-600 dark:text-emerald-400',
            detail: 'No same-profile browser run is using this profile right now.',
        };
    }, [activeBrowserProfile.profilePath, allIgRuns]);

    const selectedPostPath = useMemo(() => {
        const p = getSelectedPost();
        return (p?.post_path || '').toString().trim() || null;
    }, [getSelectedPost, selectedPostId]);

    // === Batch / Workflow handlers ===
    const resolveBatchPostPaths = useCallback((): string[] => {
        if (batchScope === 'selected') {
            return selectedPostPath ? [selectedPostPath] : [];
        }
        if (batchScope === 'filtered') {
            return filteredPostPaths;
        }
        return batchManualPostPaths
            .split('\n')
            .map((s) => s.trim())
            .filter((s) => s.length > 0);
    }, [batchScope, selectedPostPath, filteredPostPaths, batchManualPostPaths]);

    const runBatchProcessor = useCallback(async () => {
        const postPaths = resolveBatchPostPaths();
        if (postPaths.length === 0) {
            alert('No post_paths resolved. Please select scope + provide paths.');
            return;
        }

        const additionalInputs: any = {
            action: batchAction,
            post_paths: postPaths,
            strict_mode: batchStrictMode,
        };

        if (batchAction === 'batch_generate_export_packs') {
            additionalInputs.output_folder = batchOutputFolder;
        }
        if (batchAction === 'batch_update_status') {
            additionalInputs.new_status = batchNewStatus;
        }
        if (batchAction === 'batch_process') {
            additionalInputs.operations = batchOperationsText
                .split('\n')
                .map((s) => s.trim())
                .filter((s) => s.length > 0);
            try {
                additionalInputs.operation_config = JSON.parse(batchOperationConfigText);
            } catch {
                additionalInputs.operation_config = {};
            }
        }

        const result = await onRunPlaybook('ig_batch_processor', additionalInputs);
        if (result.success) {
            setBatchNotice(`Batch started: ${result.execution_id}`);
        } else {
            setBatchNotice(`Batch failed: ${result.error}`);
        }
    }, [
        resolveBatchPostPaths,
        batchAction,
        batchStrictMode,
        batchOutputFolder,
        batchNewStatus,
        batchOperationsText,
        batchOperationConfigText,
        onRunPlaybook,
    ]);

    const runCompleteWorkflow = useCallback(async () => {
        let additionalInputs: any = { workflow_type: workflowPreset };

        if (workflowPreset === 'create_post_workflow') {
            additionalInputs.post_content = workflowPostContent;
            additionalInputs.target_folder = workflowTargetFolder;
            try {
                additionalInputs.post_metadata = JSON.parse(workflowPostMetadataText);
            } catch {
                additionalInputs.post_metadata = {};
            }
        } else if (workflowPreset === 'review_workflow') {
            additionalInputs.post_path = selectedPostPath;
            try {
                additionalInputs.review_notes = JSON.parse(workflowReviewNotesText);
            } catch {
                additionalInputs.review_notes = [];
            }
        } else if (workflowPreset === 'execute_workflow') {
            try {
                additionalInputs.workflow_steps = JSON.parse(workflowStepsText);
            } catch {
                additionalInputs.workflow_steps = [];
            }
            try {
                additionalInputs.initial_context = JSON.parse(workflowInitialContextText);
            } catch {
                additionalInputs.initial_context = {};
            }
        }

        const result = await onRunPlaybook('ig_complete_workflow', additionalInputs);
        if (result.success) {
            setWorkflowNotice(`Workflow started: ${result.execution_id}`);
        } else {
            setWorkflowNotice(`Workflow failed: ${result.error}`);
        }
    }, [
        workflowPreset,
        workflowPostContent,
        workflowTargetFolder,
        workflowPostMetadataText,
        selectedPostPath,
        workflowReviewNotesText,
        workflowStepsText,
        workflowInitialContextText,
        onRunPlaybook,
    ]);

    // === Render ===
    return (
        <div className="w-80 border-l dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex flex-col">
            {/* Header */}
            <div className="px-3 py-3 border-b dark:border-gray-700">
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-gray-800/80 px-2.5 py-2">
                    <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        <span>IG Active Profile</span>
                        <div className="flex flex-wrap items-center justify-end gap-1.5">
                            <span className={`font-semibold ${activeProfileState.toneClass}`}>
                                {activeProfileState.label}
                            </span>
                            <span className={`font-semibold ${activeBrowserProfile.loggedIn
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : activeBrowserProfile.sessionExpired
                                    ? 'text-amber-600 dark:text-amber-400'
                                    : 'text-gray-500 dark:text-gray-400'
                                }`}>
                                {activeBrowserProfile.loggedIn
                                    ? 'Logged in'
                                    : activeBrowserProfile.sessionExpired
                                        ? 'Expired'
                                        : 'No session'}
                            </span>
                            <button
                                type="button"
                                onClick={activeBrowserProfile.onOpenAccess}
                                className="inline-flex items-center gap-1 rounded border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-700/50"
                                title="Open Access settings"
                            >
                                <Settings2 className="w-3 h-3" />
                                Access
                            </button>
                        </div>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                        <select
                            value={activeBrowserProfile.profileName}
                            onChange={(event) => activeBrowserProfile.onSelectProfile(event.target.value)}
                            className="min-w-0 flex-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
                            aria-label="Switch active IG browser profile"
                        >
                            {activeBrowserProfile.availableProfiles.map((profile) => (
                                <option key={profile.name} value={profile.name}>
                                    {profile.name}
                                    {profile.logged_in ? ' ✓' : profile.session_expired ? ' ⚠ expired' : ''}
                                    {profile.ig_username ? ` @${profile.ig_username}` : ''}
                                </option>
                            ))}
                            {!activeBrowserProfile.availableProfiles.some((profile) => profile.name === activeBrowserProfile.profileName) && (
                                <option value={activeBrowserProfile.profileName}>Create access: {activeBrowserProfile.profileName}</option>
                            )}
                        </select>
                        <button
                            type="button"
                            onClick={activeBrowserProfile.onRefreshStatus}
                            className="inline-flex items-center gap-1 rounded border border-gray-200 px-2 py-1.5 text-[11px] font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700/50"
                            title="Refresh profile status"
                        >
                            <RefreshCw className={`w-3 h-3 ${activeBrowserProfile.isChecking ? 'animate-spin' : ''}`} />
                            Check
                        </button>
                    </div>
                    <div className="mt-2 text-[10px] text-gray-500 dark:text-gray-400">
                        {activeProfileState.detail}
                    </div>
                </div>
            </div>

            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Tab Buttons */}
                <div className="px-3 pt-3">
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={() => setActiveTab('logs')}
                            className={`h-8 px-2 rounded-md border text-xs flex items-center gap-2 ${activeTab === 'logs'
                                ? 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-900 dark:text-gray-100'
                                : 'bg-transparent border-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                                }`}
                            aria-label="Run Logs"
                            title="Run Logs"
                        >
                            <History className="w-3.5 h-3.5" />
                            {activeTab === 'logs' && <span className="text-[11px] font-semibold uppercase tracking-wide">Run Logs</span>}
                        </button>
                        <button
                            type="button"
                            onClick={() => setActiveTab('queue')}
                            className={`h-8 px-2 rounded-md border text-xs flex items-center gap-2 ${activeTab === 'queue'
                                ? 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-900 dark:text-gray-100'
                                : 'bg-transparent border-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                                }`}
                            aria-label="Queue Explorer"
                            title="Queue Explorer"
                        >
                            <List className="w-3.5 h-3.5" />
                            {activeTab === 'queue' && <span className="text-[11px] font-semibold uppercase tracking-wide">Queue</span>}
                        </button>
                        <button
                            type="button"
                            onClick={() => setActiveTab('actions')}
                            className={`h-8 px-2 rounded-md border text-xs flex items-center gap-2 ${activeTab === 'actions'
                                ? 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-900 dark:text-gray-100'
                                : 'bg-transparent border-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                                }`}
                            aria-label="Quick Actions"
                            title="Quick Actions"
                        >
                            <Sparkles className="w-3.5 h-3.5" />
                            {activeTab === 'actions' && <span className="text-[11px] font-semibold uppercase tracking-wide">Actions</span>}
                        </button>
                        <button
                            type="button"
                            onClick={() => setActiveTab('ready')}
                            className={`h-8 px-2 rounded-md border text-xs flex items-center gap-2 ${activeTab === 'ready'
                                ? 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-900 dark:text-gray-100'
                                : 'bg-transparent border-transparent text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                                }`}
                            aria-label="Ready Score"
                            title="Ready Score"
                        >
                            <Activity className="w-3.5 h-3.5" />
                            {activeTab === 'ready' && <span className="text-[11px] font-semibold uppercase tracking-wide">Ready</span>}
                        </button>
                    </div>
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {/* Error Banner */}
                    {error && (
                        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                            <div className="flex items-start gap-2">
                                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
                                <div className="flex-1">
                                    <p className="text-xs font-semibold text-red-900 dark:text-red-100 mb-1">
                                        Execution Error
                                    </p>
                                    <p className="text-xs text-red-700 dark:text-red-300 break-words">
                                        {error}
                                    </p>
                                </div>
                                <button
                                    onClick={onDismissError}
                                    className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-200"
                                    title="Close"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Logs Tab */}
                    {activeTab === 'logs' && (
                        <div className="flex flex-col">
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 sm:p-4 shadow-sm">
                                <RunLogStatsCards
                                    counts={runLogCounts}
                                    targetsTotal={targetsTotal}
                                    activeRunCount={runningIgRuns.length}
                                />

                                {/* Active Execution Cards */}
                                {runningIgRuns.map(run => {
                                    const execId = run.execution_id || run.id;
                                    if (!execId) return null;
                                    return (
                                        <ActiveExecutionCard
                                            key={execId}
                                            workspaceId={workspaceId}
                                            apiUrl={apiUrl}
                                            igExecutionId={execId}
                                            igPinnedRun={run}
                                            igRerunAllowPartial={igRerunAllowPartial}
                                            setIgRerunAllowPartial={setIgRerunAllowPartial}
                                            cancelExecution={cancelExecution}
                                            rerunExecution={rerunExecution}
                                            canRerunStatus={canRerunStatus}
                                            cancelBusyId={cancelBusyId}
                                            rerunBusyId={rerunBusyId}
                                        />
                                    );
                                })}

                                {runningIgRuns.length === 0 && (
                                    <div className="rounded-lg border border-dashed border-gray-200 dark:border-gray-700 px-3 py-4 text-[11px] text-gray-500 dark:text-gray-400">
                                        No IG executions are actively running right now.
                                    </div>
                                )}

                                {/* Notices */}
                                {rerunNotice && (
                                    <div className="mt-3 text-[11px] rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-gray-700 dark:text-gray-200">
                                        {rerunNotice}
                                    </div>
                                )}
                                {cancelNotice && (
                                    <div className="mt-3 text-[11px] rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-gray-700 dark:text-gray-200">
                                        {cancelNotice}
                                    </div>
                                )}

                                {/* Rerun needs target input */}
                                {rerunNeedsTarget && (
                                    <div className="mt-3 text-[11px] rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-2 text-gray-700 dark:text-gray-200">
                                        <div className="mb-2">Target username is required for rerun.</div>
                                        <div className="flex items-center gap-2">
                                            <input
                                                value={rerunTargetInput}
                                                onChange={(e) => setRerunTargetInput(e.target.value)}
                                                placeholder="e.g. hannah.beezy"
                                                className="flex-1 px-2 py-1 text-xs border rounded dark:bg-gray-800 dark:border-gray-700"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => rerunExecution(rerunNeedsTarget.executionId, { target_username: rerunTargetInput.trim() })}
                                                disabled={!rerunTargetInput.trim() || rerunBusyId === rerunNeedsTarget.executionId}
                                                className="px-2 py-1 text-[10px] rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                Confirm rerun
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Queue Tab */}
                    {activeTab === 'queue' && (
                        <div className="flex flex-col">
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 sm:p-4 shadow-sm">
                                <QueueTab
                                    workspaceId={workspaceId}
                                    apiUrl={apiUrl}
                                    rerunBusyId={rerunBusyId}
                                    igRerunAllowPartial={igRerunAllowPartial}
                                    canRerunStatus={canRerunStatus}
                                    rerunExecution={rerunExecution}
                                />
                            </div>
                        </div>
                    )}

                    {/* Actions Tab */}
                    {activeTab === 'actions' && (
                        <ActionsTab
                            selectedPostId={selectedPostId}
                            selectedPostPath={selectedPostPath}
                            filteredPostPaths={filteredPostPaths}
                            isRunning={isRunning}
                            batchAction={batchAction}
                            setBatchAction={setBatchAction}
                            batchScope={batchScope}
                            setBatchScope={setBatchScope}
                            batchManualPostPaths={batchManualPostPaths}
                            setBatchManualPostPaths={setBatchManualPostPaths}
                            batchStrictMode={batchStrictMode}
                            setBatchStrictMode={setBatchStrictMode}
                            batchOutputFolder={batchOutputFolder}
                            setBatchOutputFolder={setBatchOutputFolder}
                            batchNewStatus={batchNewStatus}
                            setBatchNewStatus={setBatchNewStatus}
                            batchOperationsText={batchOperationsText}
                            setBatchOperationsText={setBatchOperationsText}
                            batchOperationConfigText={batchOperationConfigText}
                            setBatchOperationConfigText={setBatchOperationConfigText}
                            batchNotice={batchNotice}
                            workflowPreset={workflowPreset}
                            setWorkflowPreset={setWorkflowPreset}
                            workflowTargetFolder={workflowTargetFolder}
                            setWorkflowTargetFolder={setWorkflowTargetFolder}
                            workflowPostContent={workflowPostContent}
                            setWorkflowPostContent={setWorkflowPostContent}
                            workflowPostMetadataText={workflowPostMetadataText}
                            setWorkflowPostMetadataText={setWorkflowPostMetadataText}
                            workflowStepsText={workflowStepsText}
                            setWorkflowStepsText={setWorkflowStepsText}
                            workflowInitialContextText={workflowInitialContextText}
                            setWorkflowInitialContextText={setWorkflowInitialContextText}
                            workflowReviewNotesText={workflowReviewNotesText}
                            setWorkflowReviewNotesText={setWorkflowReviewNotesText}
                            workflowNotice={workflowNotice}
                            onRunPlaybook={onRunPlaybook}
                            runBatchProcessor={runBatchProcessor}
                            runCompleteWorkflow={runCompleteWorkflow}
                        />
                    )}

                    {/* Ready Tab */}
                    {activeTab === 'ready' && (
                        <div>
                            <ReadyScore post={getSelectedPost()} apiUrl={apiUrl} workspaceId={workspaceId} />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default WorkbenchExecutionPanel;
