'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useT } from '@/lib/i18n';
import { formatLocalDateTime } from '@/lib/time';
import { getApiBaseUrl } from '../../../../lib/api-url';
import { GovernedMemoryPreview } from '../../../../components/workspace/governance/GovernedMemoryPreview';
import { MemoryImpactGraphPanel } from '../../../../components/workspace/governance/MemoryImpactGraphPanel';
import { WorkflowEvidenceSummary } from '../../../../components/workspace/meeting/WorkflowEvidenceSummary';
import { subscribeEventStream } from '../../../../components/workspace/eventProjector';
import {
    buildPdScenePatchSuccessText,
    buildScenePatchFailureText,
    ScenePatchConsole,
    buildScenePatchSummary,
    parseScenePatchJson,
    scenePatchResultMessage,
} from '../../../../components/workspace/ScenePatchConsole';

const API_URL = getApiBaseUrl();

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MeetingSession {
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
    compile_job?: CompileJobSummary | null;
}

interface CompileJobSummary {
    id: string;
    status: 'accepted' | 'running' | 'succeeded' | 'failed' | string;
    session_id?: string | null;
    error?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    metadata?: Record<string, any>;
}

interface CanonicalMemoryLink {
    memory_item_id: string;
    digest_id?: string;
    writeback_run_id?: string;
    lifecycle_status?: string;
    verification_status?: string;
}

interface WorkflowEvidenceDiagnostics {
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

interface RoundRoutingGoal {
    summary?: string;
    agenda_focus?: string[];
    critical_constraints?: string[];
}

interface RoundRoutingPacket {
    id: string;
    packet_type: string;
    packet_scope: 'global' | 'sparse' | string;
    consumer_role_ids?: string[];
    summary?: string;
}

interface RoundRoutingEdge {
    source_role_id: string;
    target_role_id: string;
    packet_ids?: string[];
    matched_need_ids?: string[];
    rationale?: string;
}

interface RoundRoutingRolePacketStats {
    status?: 'healthy' | 'global_only' | 'starved' | 'idle' | string;
    visible_packet_count?: number;
    global_packet_count?: number;
    sparse_packet_count?: number;
    matched_need_count?: number;
    required_need_count?: number;
    incremental_need_count?: number;
    unmatched_required_need_count?: number;
    estimated_context_chars?: number;
    visible_packet_types?: string[];
}

interface RoundRoutingMetadata extends Record<string, any> {
    role_packet_stats?: Record<string, RoundRoutingRolePacketStats>;
    starved_role_ids?: string[];
    global_only_role_ids?: string[];
    diagnostic_flags?: string[];
    largest_context_role_id?: string | null;
    max_estimated_context_chars?: number;
    next_role_id?: string;
    routing_prompt_mode?: 'sparse' | 'compressed_sparse' | 'full_context_fallback' | string;
    routing_prompt_reason?: string;
    routing_prompt_role_id?: string;
    compressed_packet_char_limit?: number;
}

interface RoundRoutingWarning {
    meeting_session_id?: string;
    round_number?: number;
    routing_stage?: string;
    next_role_id?: string | null;
    severity?: 'high' | 'medium' | string;
    warning_types?: string[];
    starved_role_ids?: string[];
    global_only_role_ids?: string[];
    diagnostic_flags?: string[];
    largest_context_role_id?: string | null;
    max_estimated_context_chars?: number;
    routing_prompt_mode?: 'sparse' | 'compressed_sparse' | 'full_context_fallback' | string;
    routing_prompt_reason?: string;
    routing_prompt_role_id?: string | null;
    compressed_packet_char_limit?: number;
    summary?: string;
    detected_at?: string;
}

interface RoundRoutingPromptDecision {
    meeting_session_id?: string;
    round_number?: number;
    routing_stage?: string;
    role_id?: string;
    prompt_mode?: 'sparse' | 'compressed_sparse' | 'full_context_fallback' | string;
    reason?: string;
    estimated_context_chars?: number;
    visible_packet_count?: number;
    sparse_packet_count?: number;
    compressed_packet_char_limit?: number;
    recorded_at?: string;
}

interface RoundRoutingPromptSummary {
    total_decisions?: number;
    sparse_count?: number;
    compressed_count?: number;
    fallback_count?: number;
    adaptive_count?: number;
    sparse_ratio?: number;
    compressed_ratio?: number;
    fallback_ratio?: number;
    adaptive_ratio?: number;
    last_prompt_mode?: 'sparse' | 'compressed_sparse' | 'full_context_fallback' | string;
    last_prompt_role_id?: string;
    last_prompt_reason?: string;
    last_round_number?: number;
    last_recorded_at?: string;
    health_status?: 'healthy' | 'warning' | 'critical' | string;
    health_reason?: string;
}

interface RoundRoutingGraph {
    round_number: number;
    goal?: RoundRoutingGoal;
    packets?: RoundRoutingPacket[];
    edges?: RoundRoutingEdge[];
    unmatched_need_ids?: string[];
    unmatched_packet_ids?: string[];
    fixed_speaker_order?: string[];
    metadata?: RoundRoutingMetadata;
}

interface ActionItem {
    description?: string;
    status?: string;
    assignee?: string;
    [key: string]: any;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusStyle(status: string): string {
    const styles: Record<string, string> = {
        active: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        planned: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
        closing: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
        closed: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
        aborted: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[status] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getCompileJobStyle(status?: string | null): string {
    const styles: Record<string, string> = {
        accepted: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
        running: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
        succeeded: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[status || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getCompileJobLabel(status?: string | null): string {
    const labels: Record<string, string> = {
        accepted: 'accepted',
        running: 'running',
        succeeded: 'succeeded',
        failed: 'failed',
    };
    return labels[status || ''] || 'unknown';
}

function describeCompileJob(job?: CompileJobSummary | null): string {
    if (!job) {
        return '';
    }
    if (job.status === 'failed') {
        return job.error?.trim() || 'compile failed';
    }
    if (job.status === 'accepted') {
        return 'compile accepted and queued';
    }
    if (job.status === 'running') {
        return 'compile is still running';
    }
    return 'compile completed';
}

function formatWorkflowEvidenceLabel(label: string): string {
    return label.replace(/^Recent /, '').replace(/^Latest /, '');
}

function formatRoleLabel(roleId: string): string {
    if (!roleId) {
        return 'Unknown';
    }
    return roleId.charAt(0).toUpperCase() + roleId.slice(1);
}

function getRoutingDiagnosticStyle(status?: string): string {
    const styles: Record<string, string> = {
        healthy: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
        global_only: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
        starved: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        idle: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    };
    return styles[status || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getRoutingDiagnosticLabel(status?: string): string {
    const labels: Record<string, string> = {
        healthy: 'healthy',
        global_only: 'global-only',
        starved: 'starved',
        idle: 'idle',
    };
    return labels[status || ''] || 'unknown';
}

function getRoutingWarningStyle(severity?: string): string {
    const styles: Record<string, string> = {
        high: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
    };
    return styles[severity || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getRoutingPromptModeStyle(mode?: string): string {
    const styles: Record<string, string> = {
        sparse: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
        compressed_sparse: 'bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-900/40 dark:text-fuchsia-300',
        full_context_fallback: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[mode || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getRoutingPromptModeLabel(mode?: string): string {
    const labels: Record<string, string> = {
        sparse: 'sparse mode',
        compressed_sparse: 'compressed sparse',
        full_context_fallback: 'full-context fallback',
    };
    return labels[mode || ''] || 'prompt mode unknown';
}

function formatRatioPercent(value?: number): string {
    return `${Math.round((value || 0) * 100)}%`;
}

function getRoutingHealthStyle(status?: string): string {
    const styles: Record<string, string> = {
        healthy: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
        warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
        critical: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[status || ''] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getRoutingHealthLabel(status?: string): string {
    const labels: Record<string, string> = {
        healthy: 'routing stable',
        warning: 'routing pressure',
        critical: 'routing fallback risk',
    };
    return labels[status || ''] || 'routing health unknown';
}

function getRoutingHealthReasonLabel(reason?: string): string {
    const labels: Record<string, string> = {
        stable_sparse: 'stable sparse routing',
        compression_pressure: 'compression pressure',
        fallback_present: 'fallback observed',
        fallback_pressure: 'repeated fallback pressure',
    };
    return labels[reason || ''] || 'routing health signal';
}

function deriveRoutingHealthSummary(
    summary?: RoundRoutingPromptSummary,
): RoundRoutingPromptSummary | undefined {
    if (!summary?.total_decisions) {
        return summary;
    }
    if (summary.health_status) {
        return summary;
    }
    const fallbackCount = Number(summary.fallback_count || 0);
    const fallbackRatio = Number(summary.fallback_ratio || 0);
    const compressedRatio = Number(summary.compressed_ratio || 0);
    const adaptiveRatio = Number(summary.adaptive_ratio || 0);
    let healthStatus: RoundRoutingPromptSummary['health_status'] = 'healthy';
    let healthReason: RoundRoutingPromptSummary['health_reason'] = 'stable_sparse';
    if (fallbackCount >= 2 || fallbackRatio >= 0.5) {
        healthStatus = 'critical';
        healthReason = 'fallback_pressure';
    } else if (fallbackCount >= 1) {
        healthStatus = 'warning';
        healthReason = 'fallback_present';
    } else if (compressedRatio >= 0.5 || adaptiveRatio >= 0.5) {
        healthStatus = 'warning';
        healthReason = 'compression_pressure';
    }
    return {
        ...summary,
        health_status: healthStatus,
        health_reason: healthReason,
    };
}

function describeRoutingHealth(summary?: RoundRoutingPromptSummary): string {
    if (!summary?.total_decisions) {
        return '';
    }
    return `routing · fallback ${formatRatioPercent(summary.fallback_ratio)} · compressed ${formatRatioPercent(summary.compressed_ratio)}`;
}

function getRoundRoutingRolePacketStats(
    graph?: RoundRoutingGraph,
): Array<RoundRoutingRolePacketStats & { role_id: string }> {
    const rolePacketStats = graph?.metadata?.role_packet_stats || {};
    const orderedRoleIds = [
        ...(graph?.fixed_speaker_order || []),
        ...Object.keys(rolePacketStats),
    ].filter((roleId, index, values) => values.indexOf(roleId) === index);

    return orderedRoleIds
        .filter((roleId) => rolePacketStats[roleId])
        .map((roleId) => ({
            role_id: roleId,
            ...rolePacketStats[roleId],
        }));
}

// ---------------------------------------------------------------------------
// Session Card (list item)
// ---------------------------------------------------------------------------

function SessionCard({
    session,
    isSelected,
    onClick,
}: {
    session: MeetingSession;
    isSelected: boolean;
    onClick: () => void;
}) {
    const actionItemCount = session.action_items?.length || 0;
    const workflowEvidenceDiagnostics =
        session.metadata?.workflow_evidence_diagnostics as WorkflowEvidenceDiagnostics | undefined;
    const routingPromptModeSummary = deriveRoutingHealthSummary(
        session.metadata?.round_routing_prompt_mode_summary as
            | RoundRoutingPromptSummary
            | undefined,
    );

    return (
        <div
            className={`relative flex items-start gap-4 cursor-pointer p-4 rounded-lg transition-colors ${isSelected
                    ? 'bg-sky-50 dark:bg-sky-900/20 ring-1 ring-sky-300 dark:ring-sky-700'
                    : 'hover:bg-surface-secondary dark:hover:bg-gray-800'
                }`}
            onClick={onClick}
        >
            {/* Timeline dot */}
            <div
                className={`relative z-10 w-4 h-4 rounded-full border-2 flex-shrink-0 mt-1 ${session.is_active
                        ? 'bg-green-500 border-green-300 dark:border-green-700'
                        : 'bg-gray-400 border-gray-300 dark:bg-gray-500 dark:border-gray-600'
                    }`}
            />

            {/* Content */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${getStatusStyle(session.status)}`}>
                        {session.status}
                    </span>
                    {session.compile_job && (
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${getCompileJobStyle(session.compile_job.status)}`}>
                            compile {getCompileJobLabel(session.compile_job.status)}
                        </span>
                    )}
                    {routingPromptModeSummary?.total_decisions && (
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${getRoutingHealthStyle(routingPromptModeSummary.health_status)}`}>
                            {getRoutingHealthLabel(routingPromptModeSummary.health_status)}
                        </span>
                    )}
                    <span className="text-xs text-secondary dark:text-gray-400">
                        {session.meeting_type}
                    </span>
                </div>

                <div className="text-sm text-primary dark:text-gray-200 mb-1">
                    Round {session.round_count}/{session.max_rounds}
                    {actionItemCount > 0 && (
                        <span className="ml-2 text-xs text-sky-700 dark:text-sky-400">
                            · {actionItemCount} action items
                        </span>
                    )}
                </div>

                {workflowEvidenceDiagnostics && (
                    <div className="mb-1 text-xs text-secondary dark:text-gray-400">
                        workflow packet · {workflowEvidenceDiagnostics.profile || 'general'} · {workflowEvidenceDiagnostics.scope || 'none'} · {workflowEvidenceDiagnostics.selected_line_count || 0}/{workflowEvidenceDiagnostics.total_line_budget || 0} lines
                    </div>
                )}

                {session.compile_job && (
                    <div className="mb-1 text-xs text-secondary dark:text-gray-400">
                        {describeCompileJob(session.compile_job)}
                    </div>
                )}

                {routingPromptModeSummary?.total_decisions && (
                    <div className="mb-1 text-xs text-secondary dark:text-gray-400">
                        {describeRoutingHealth(routingPromptModeSummary)}
                    </div>
                )}

                <div className="text-xs text-secondary dark:text-gray-500">
                    {formatLocalDateTime(session.started_at)}
                    {session.ended_at && (
                        <span className="ml-2">
                            → {formatLocalDateTime(session.ended_at)}
                        </span>
                    )}
                </div>

                {/* Minutes preview */}
                {session.minutes_md && (
                    <div className="mt-1.5 text-xs text-tertiary dark:text-gray-500 line-clamp-2 italic">
                        {session.minutes_md.slice(0, 120)}
                        {session.minutes_md.length > 120 && '…'}
                    </div>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Detail Panel
// ---------------------------------------------------------------------------

function SessionDetail({
    session,
    workspaceId,
    autoOpenScenePatch = false,
    onClose,
}: {
    session: MeetingSession;
    workspaceId: string;
    autoOpenScenePatch?: boolean;
    onClose: () => void;
}) {
    const router = useRouter();
    const t = useT();
    const [showScenePatchPanel, setShowScenePatchPanel] = useState(autoOpenScenePatch);
    const [scenePatchJson, setScenePatchJson] = useState('');
    const [patchSceneId, setPatchSceneId] = useState('');
    const [artifactId, setArtifactId] = useState('');
    const [applyingScenePatch, setApplyingScenePatch] = useState(false);
    const [scenePatchResult, setScenePatchResult] = useState<string | null>(null);
    const actionItems = session.action_items || [];
    const decisions = session.decisions || [];
    const agenda = session.agenda || [];
    const canonicalMemory = session.metadata?.canonical_memory as CanonicalMemoryLink | undefined;
    const workflowEvidenceDiagnostics =
        session.metadata?.workflow_evidence_diagnostics as WorkflowEvidenceDiagnostics | undefined;
    const roundRoutingGraph =
        session.metadata?.last_round_routing_graph as RoundRoutingGraph | undefined;
    const roundRoutingWarning =
        session.metadata?.last_round_routing_warning as RoundRoutingWarning | undefined;
    const routingPromptModeCounts =
        session.metadata?.round_routing_prompt_mode_counts as Record<string, number> | undefined;
    const persistedRoutingPromptModeSummary =
        session.metadata?.round_routing_prompt_mode_summary as RoundRoutingPromptSummary | undefined;
    const routingPromptModeHistory = useMemo(
        () =>
            (
                (session.metadata?.round_routing_prompt_mode_history ||
                    []) as RoundRoutingPromptDecision[]
            )
                .slice(-6)
                .reverse(),
        [session.metadata?.round_routing_prompt_mode_history],
    );
    const routingPromptModeSummary = useMemo<RoundRoutingPromptSummary | undefined>(() => {
        if (persistedRoutingPromptModeSummary?.total_decisions) {
            return deriveRoutingHealthSummary(persistedRoutingPromptModeSummary);
        }
        if (!routingPromptModeCounts || Object.keys(routingPromptModeCounts).length === 0) {
            return undefined;
        }
        const total = Object.values(routingPromptModeCounts).reduce(
            (sum, count) => sum + Number(count || 0),
            0,
        );
        if (!total) {
            return undefined;
        }
        const sparseCount = Number(routingPromptModeCounts.sparse || 0);
        const compressedCount = Number(routingPromptModeCounts.compressed_sparse || 0);
        const fallbackCount = Number(routingPromptModeCounts.full_context_fallback || 0);
        const lastEntry = routingPromptModeHistory[0];
        return deriveRoutingHealthSummary({
            total_decisions: total,
            sparse_count: sparseCount,
            compressed_count: compressedCount,
            fallback_count: fallbackCount,
            adaptive_count: compressedCount + fallbackCount,
            sparse_ratio: sparseCount / total,
            compressed_ratio: compressedCount / total,
            fallback_ratio: fallbackCount / total,
            adaptive_ratio: (compressedCount + fallbackCount) / total,
            last_prompt_mode: lastEntry?.prompt_mode,
            last_prompt_role_id: lastEntry?.role_id,
            last_prompt_reason: lastEntry?.reason,
            last_round_number: lastEntry?.round_number,
            last_recorded_at: lastEntry?.recorded_at,
        });
    }, [
        persistedRoutingPromptModeSummary,
        routingPromptModeCounts,
        routingPromptModeHistory,
    ]);
    const roundRoutingRolePacketStats = useMemo(
        () => getRoundRoutingRolePacketStats(roundRoutingGraph),
        [roundRoutingGraph],
    );
    const roundRoutingStarvedRoles = roundRoutingGraph?.metadata?.starved_role_ids || [];
    const roundRoutingGlobalOnlyRoles = roundRoutingGraph?.metadata?.global_only_role_ids || [];
    const workflowEvidenceSections = (workflowEvidenceDiagnostics?.section_order || [])
        .map((title) => ({
            title,
            candidateCount: workflowEvidenceDiagnostics?.candidate_counts?.[title] || 0,
            selectedCount: workflowEvidenceDiagnostics?.selected_counts?.[title] || 0,
            droppedCount: workflowEvidenceDiagnostics?.dropped_counts?.[title] || 0,
            limit: workflowEvidenceDiagnostics?.section_limits?.[title] || 0,
        }))
        .filter(
            (section) =>
                section.candidateCount > 0 ||
                section.selectedCount > 0 ||
                section.limit > 0
        );

    const parsedScenePatch = useMemo(
        () => parseScenePatchJson(scenePatchJson),
        [scenePatchJson],
    );

    const scenePatchSummary = useMemo(
        () => buildScenePatchSummary(parsedScenePatch.patch, patchSceneId),
        [parsedScenePatch.patch, patchSceneId],
    );
    const scenePatchResultView = useMemo(
        () => scenePatchResultMessage(scenePatchResult),
        [scenePatchResult],
    );

    useEffect(() => {
        const sourceSceneId = parsedScenePatch.patch?.source_scene_id;
        if (sourceSceneId && !patchSceneId.trim()) {
            setPatchSceneId(sourceSceneId);
        }
    }, [parsedScenePatch.patch?.source_scene_id, patchSceneId]);

    useEffect(() => {
        if (autoOpenScenePatch) {
            setShowScenePatchPanel(true);
        }
    }, [autoOpenScenePatch, session.id]);

    const applyScenePatch = useCallback(async () => {
        if (!parsedScenePatch.patch) {
            setScenePatchResult(
                parsedScenePatch.error
                    ? t('meetingsScenePatchParseFailed', { error: parsedScenePatch.error })
                    : t('meetingsScenePatchJsonRequired'),
            );
            return;
        }
        if (!patchSceneId.trim()) {
            setScenePatchResult(t('meetingsScenePatchSceneIdRequired'));
            return;
        }
        try {
            setApplyingScenePatch(true);
            setScenePatchResult(null);
            const response = await fetch(
                `${API_URL}/api/v1/capabilities/performance_direction/sessions/${encodeURIComponent(session.id)}/storyboard/scene-patch`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scene_id: patchSceneId.trim(),
                        artifact_id: artifactId.trim() || undefined,
                        storyboard_scene_patch: parsedScenePatch.patch,
                    }),
                }
            );
            if (!response.ok) {
                const detail = await response.text();
                throw new Error(detail || `HTTP ${response.status}`);
            }
            const payload = await response.json();
            setScenePatchResult(
                buildPdScenePatchSuccessText({
                    sceneId: payload.patched_scene_id || patchSceneId.trim(),
                    artifactId: payload.artifact?.artifact_id || null,
                })
            );
        } catch (error) {
            setScenePatchResult(buildScenePatchFailureText('PD', error));
        } finally {
            setApplyingScenePatch(false);
        }
    }, [artifactId, parsedScenePatch.error, parsedScenePatch.patch, patchSceneId, session.id, t]);

    return (
        <div className="p-5 space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    Session Detail
                </h2>
                <button
                    onClick={onClose}
                    className="text-secondary hover:text-primary dark:hover:text-gray-300 text-lg"
                >
                    ✕
                </button>
            </div>

            {/* Status + Rounds */}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Status
                    </label>
                    <div className="mt-1">
                        <span className={`text-xs px-2 py-1 rounded ${getStatusStyle(session.status)}`}>
                            {session.status}
                        </span>
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Rounds
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {session.round_count} / {session.max_rounds}
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Type
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {session.meeting_type}
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Started
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {formatLocalDateTime(session.started_at)}
                    </div>
                </div>
            </div>

            {session.compile_job && (
                <div className="rounded-lg border border-default dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-3">
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Compile Job
                    </label>
                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                        <span className={`text-xs px-2 py-1 rounded ${getCompileJobStyle(session.compile_job.status)}`}>
                            {getCompileJobLabel(session.compile_job.status)}
                        </span>
                        <span className="text-xs text-secondary dark:text-gray-400">
                            {describeCompileJob(session.compile_job)}
                        </span>
                    </div>
                    <div className="mt-2 text-xs text-tertiary dark:text-gray-500">
                        Job {session.compile_job.id}
                    </div>
                </div>
            )}

            {roundRoutingWarning && (
                <div className="rounded-lg border border-amber-200 dark:border-amber-900/40 bg-amber-50/80 dark:bg-amber-950/20 p-3 space-y-2">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <label className="text-[10px] font-medium text-amber-800 dark:text-amber-300 uppercase tracking-wide">
                                Latest Routing Warning
                            </label>
                            <div className="mt-1 text-sm text-amber-950 dark:text-amber-100">
                                {roundRoutingWarning.summary || 'Routing diagnostics flagged a warning.'}
                            </div>
                        </div>
                        <span className={`text-[10px] px-2 py-1 rounded ${getRoutingWarningStyle(roundRoutingWarning.severity)}`}>
                            {roundRoutingWarning.severity || 'warning'}
                        </span>
                    </div>
                    <div className="text-xs text-amber-900/80 dark:text-amber-200/80">
                        round {roundRoutingWarning.round_number || '?'}
                        {roundRoutingWarning.next_role_id && (
                            <span> · before {formatRoleLabel(roundRoutingWarning.next_role_id)}</span>
                        )}
                        {roundRoutingWarning.detected_at && (
                            <span> · {formatLocalDateTime(roundRoutingWarning.detected_at)}</span>
                        )}
                    </div>
                    {((roundRoutingWarning.warning_types?.length || 0) > 0 || (roundRoutingWarning.max_estimated_context_chars || 0) > 0) && (
                        <div className="text-xs text-amber-900/80 dark:text-amber-200/80">
                            {(roundRoutingWarning.warning_types || []).join(' · ')}
                            {(roundRoutingWarning.max_estimated_context_chars || 0) > 0 && (
                                <span> · max ctx ~{roundRoutingWarning.max_estimated_context_chars || 0} chars</span>
                            )}
                            {roundRoutingWarning.largest_context_role_id && (
                                <span> · hot spot {formatRoleLabel(roundRoutingWarning.largest_context_role_id)}</span>
                            )}
                        </div>
                    )}
                    {roundRoutingWarning.routing_prompt_mode && (
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(roundRoutingWarning.routing_prompt_mode)}`}>
                                {getRoutingPromptModeLabel(roundRoutingWarning.routing_prompt_mode)}
                            </span>
                            {roundRoutingWarning.routing_prompt_role_id && (
                                <span className="text-xs text-amber-900/80 dark:text-amber-200/80">
                                    for {formatRoleLabel(roundRoutingWarning.routing_prompt_role_id)}
                                </span>
                            )}
                            {roundRoutingWarning.routing_prompt_reason && (
                                <span className="text-xs text-amber-900/80 dark:text-amber-200/80">
                                    reason {roundRoutingWarning.routing_prompt_reason}
                                </span>
                            )}
                            {(roundRoutingWarning.compressed_packet_char_limit || 0) > 0 && (
                                <span className="text-xs text-amber-900/80 dark:text-amber-200/80">
                                    preview limit {roundRoutingWarning.compressed_packet_char_limit} chars
                                </span>
                            )}
                        </div>
                    )}
                </div>
            )}

            {roundRoutingGraph && (
                <div className="rounded-lg border border-default dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-4 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Round Routing
                            </label>
                            <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                round {roundRoutingGraph.round_number} · {roundRoutingGraph.edges?.length || 0} edges · {roundRoutingGraph.packets?.length || 0} packets
                            </div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap justify-end">
                            {(roundRoutingGraph.metadata?.global_briefing_retained ?? true) && (
                                <span className="text-[10px] px-2 py-1 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                                    global briefing kept
                                </span>
                            )}
                            {roundRoutingGraph.metadata?.sparse_incremental_packets && (
                                <span className="text-[10px] px-2 py-1 rounded bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300">
                                    sparse packets
                                </span>
                            )}
                            {roundRoutingGraph.metadata?.next_role_id && (
                                <span className="text-[10px] px-2 py-1 rounded bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300">
                                    next {formatRoleLabel(roundRoutingGraph.metadata.next_role_id)}
                                </span>
                            )}
                            {roundRoutingGraph.metadata?.routing_prompt_mode && (
                                <span className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(roundRoutingGraph.metadata.routing_prompt_mode)}`}>
                                    {getRoutingPromptModeLabel(roundRoutingGraph.metadata.routing_prompt_mode)}
                                </span>
                            )}
                            {(roundRoutingGraph.metadata?.max_estimated_context_chars || 0) > 0 && (
                                <span className="text-[10px] px-2 py-1 rounded bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                                    max ctx ~{roundRoutingGraph.metadata?.max_estimated_context_chars || 0} chars
                                </span>
                            )}
                            {roundRoutingStarvedRoles.length > 0 && (
                                <span className="text-[10px] px-2 py-1 rounded bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
                                    starvation risk
                                </span>
                            )}
                            {roundRoutingGlobalOnlyRoles.length > 0 && (
                                <span className="text-[10px] px-2 py-1 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                                    global-only roles
                                </span>
                            )}
                        </div>
                    </div>

                    {roundRoutingGraph.goal?.summary && (
                        <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Round Goal
                            </div>
                            <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                {roundRoutingGraph.goal.summary}
                            </div>
                        </div>
                    )}

                    {(roundRoutingGraph.goal?.agenda_focus?.length || roundRoutingGraph.goal?.critical_constraints?.length) ? (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            {(roundRoutingGraph.goal?.agenda_focus?.length || 0) > 0 && (
                                <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                                    <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                        Agenda Focus
                                    </div>
                                    <div className="mt-1 space-y-1">
                                        {(roundRoutingGraph.goal?.agenda_focus || []).map((item) => (
                                            <div key={item} className="text-xs text-primary dark:text-gray-100">
                                                {item}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {(roundRoutingGraph.goal?.critical_constraints?.length || 0) > 0 && (
                                <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                                    <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                        Constraints
                                    </div>
                                    <div className="mt-1 space-y-1">
                                        {(roundRoutingGraph.goal?.critical_constraints || []).map((item) => (
                                            <div key={item} className="text-xs text-primary dark:text-gray-100">
                                                {item}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : null}

                    {(roundRoutingGraph.metadata?.routing_prompt_mode || roundRoutingGraph.metadata?.routing_prompt_reason) && (
                        <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Prompt Path
                            </div>
                            <div className="mt-1 flex items-center gap-2 flex-wrap">
                                {roundRoutingGraph.metadata?.routing_prompt_mode && (
                                    <span className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(roundRoutingGraph.metadata.routing_prompt_mode)}`}>
                                        {getRoutingPromptModeLabel(roundRoutingGraph.metadata.routing_prompt_mode)}
                                    </span>
                                )}
                                {roundRoutingGraph.metadata?.routing_prompt_role_id && (
                                    <span className="text-xs text-secondary dark:text-gray-400">
                                        target {formatRoleLabel(roundRoutingGraph.metadata.routing_prompt_role_id)}
                                    </span>
                                )}
                                {roundRoutingGraph.metadata?.routing_prompt_reason && (
                                    <span className="text-xs text-secondary dark:text-gray-400">
                                        reason {roundRoutingGraph.metadata.routing_prompt_reason}
                                    </span>
                                )}
                                {(roundRoutingGraph.metadata?.compressed_packet_char_limit || 0) > 0 && (
                                    <span className="text-xs text-secondary dark:text-gray-400">
                                        preview limit {roundRoutingGraph.metadata?.compressed_packet_char_limit || 0} chars
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {((routingPromptModeCounts && Object.keys(routingPromptModeCounts).length > 0) || routingPromptModeHistory.length > 0) && (
                        <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2 space-y-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Prompt Mode History
                            </div>
                            {routingPromptModeSummary && (
                                <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                                    <div className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2">
                                        <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                            Total Decisions
                                        </div>
                                        <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                            {routingPromptModeSummary.total_decisions || 0}
                                        </div>
                                    </div>
                                    <div className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2">
                                        <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                            Routing Health
                                        </div>
                                        <div className="mt-1 flex items-center gap-2 flex-wrap">
                                            {routingPromptModeSummary.health_status && (
                                                <span className={`text-[10px] px-2 py-1 rounded ${getRoutingHealthStyle(routingPromptModeSummary.health_status)}`}>
                                                    {getRoutingHealthLabel(routingPromptModeSummary.health_status)}
                                                </span>
                                            )}
                                        </div>
                                        {routingPromptModeSummary.health_reason && (
                                            <div className="mt-1 text-[11px] text-tertiary dark:text-gray-500">
                                                {getRoutingHealthReasonLabel(routingPromptModeSummary.health_reason)}
                                            </div>
                                        )}
                                    </div>
                                    <div className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2">
                                        <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                            Fallback Ratio
                                        </div>
                                        <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                            {formatRatioPercent(routingPromptModeSummary.fallback_ratio)}
                                        </div>
                                        <div className="mt-1 text-[11px] text-tertiary dark:text-gray-500">
                                            {routingPromptModeSummary.fallback_count || 0} decisions
                                        </div>
                                    </div>
                                    <div className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2">
                                        <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                            Compressed Ratio
                                        </div>
                                        <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                            {formatRatioPercent(routingPromptModeSummary.compressed_ratio)}
                                        </div>
                                        <div className="mt-1 text-[11px] text-tertiary dark:text-gray-500">
                                            {routingPromptModeSummary.compressed_count || 0} decisions
                                        </div>
                                    </div>
                                    <div className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2">
                                        <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                            Last Prompt
                                        </div>
                                        <div className="mt-1 flex items-center gap-2 flex-wrap">
                                            {routingPromptModeSummary.last_prompt_mode && (
                                                <span className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(routingPromptModeSummary.last_prompt_mode)}`}>
                                                    {getRoutingPromptModeLabel(routingPromptModeSummary.last_prompt_mode)}
                                                </span>
                                            )}
                                            {routingPromptModeSummary.last_prompt_role_id && (
                                                <span className="text-[11px] text-tertiary dark:text-gray-500">
                                                    {formatRoleLabel(routingPromptModeSummary.last_prompt_role_id)}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                            {(routingPromptModeCounts && Object.keys(routingPromptModeCounts).length > 0) && (
                                <div className="flex items-center gap-2 flex-wrap">
                                    {Object.entries(routingPromptModeCounts).map(([mode, count]) => (
                                        <span
                                            key={mode}
                                            className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(mode)}`}
                                        >
                                            {getRoutingPromptModeLabel(mode)} × {count}
                                        </span>
                                    ))}
                                </div>
                            )}
                            {routingPromptModeHistory.length > 0 && (
                                <div className="space-y-2">
                                    {routingPromptModeHistory.map((entry) => (
                                        <div
                                            key={`${entry.round_number || 0}-${entry.role_id || 'unknown'}-${entry.recorded_at || ''}`}
                                            className="rounded-md bg-white/70 dark:bg-gray-900/30 px-3 py-2"
                                        >
                                            <div className="flex items-center justify-between gap-3 flex-wrap">
                                                <div className="text-xs text-primary dark:text-gray-100">
                                                    round {entry.round_number || '?'}
                                                    {entry.role_id && (
                                                        <span> · {formatRoleLabel(entry.role_id)}</span>
                                                    )}
                                                    {entry.routing_stage && (
                                                        <span> · {entry.routing_stage}</span>
                                                    )}
                                                </div>
                                                {entry.prompt_mode && (
                                                    <span className={`text-[10px] px-2 py-1 rounded ${getRoutingPromptModeStyle(entry.prompt_mode)}`}>
                                                        {getRoutingPromptModeLabel(entry.prompt_mode)}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                                                {entry.reason && <span>reason {entry.reason}</span>}
                                                {(entry.estimated_context_chars || 0) > 0 && (
                                                    <span> · ~{entry.estimated_context_chars || 0} chars</span>
                                                )}
                                                {(entry.visible_packet_count || 0) > 0 && (
                                                    <span> · {entry.visible_packet_count || 0} packets</span>
                                                )}
                                                {(entry.sparse_packet_count || 0) > 0 && (
                                                    <span> · {entry.sparse_packet_count || 0} sparse</span>
                                                )}
                                                {(entry.compressed_packet_char_limit || 0) > 0 && (
                                                    <span> · preview limit {entry.compressed_packet_char_limit} chars</span>
                                                )}
                                            </div>
                                            {entry.recorded_at && (
                                                <div className="mt-1 text-[11px] text-tertiary dark:text-gray-500">
                                                    {formatLocalDateTime(entry.recorded_at)}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {roundRoutingRolePacketStats.length > 0 && (
                        <div className="space-y-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Routing Diagnostics
                            </div>
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                {roundRoutingRolePacketStats.map((roleStats) => (
                                    <div
                                        key={roleStats.role_id}
                                        className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="text-sm text-primary dark:text-gray-100">
                                                {formatRoleLabel(roleStats.role_id)}
                                            </div>
                                            <span className={`text-[10px] px-2 py-1 rounded ${getRoutingDiagnosticStyle(roleStats.status)}`}>
                                                {getRoutingDiagnosticLabel(roleStats.status)}
                                            </span>
                                        </div>
                                        <div className="mt-1 text-xs text-secondary dark:text-gray-400">
                                            {roleStats.visible_packet_count || 0} packets · {roleStats.sparse_packet_count || 0} sparse · ~{roleStats.estimated_context_chars || 0} chars
                                        </div>
                                        <div className="mt-1 text-xs text-tertiary dark:text-gray-500">
                                            needs {roleStats.matched_need_count || 0}/{roleStats.required_need_count || 0}
                                            {(roleStats.incremental_need_count || 0) > 0 && (
                                                <span> · incremental {roleStats.incremental_need_count || 0}</span>
                                            )}
                                            {(roleStats.unmatched_required_need_count || 0) > 0 && (
                                                <span> · unmet {roleStats.unmatched_required_need_count || 0}</span>
                                            )}
                                        </div>
                                        {(roleStats.visible_packet_types?.length || 0) > 0 && (
                                            <div className="mt-1 text-[11px] text-tertiary dark:text-gray-500">
                                                {(roleStats.visible_packet_types || []).join(' · ')}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {(roundRoutingGraph.edges?.length || 0) > 0 && (
                        <div className="space-y-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Routed Edges
                            </div>
                            <div className="space-y-2">
                                {(roundRoutingGraph.edges || []).map((edge) => (
                                    <div
                                        key={`${edge.source_role_id}-${edge.target_role_id}`}
                                        className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="text-sm text-primary dark:text-gray-100">
                                                {formatRoleLabel(edge.source_role_id)} → {formatRoleLabel(edge.target_role_id)}
                                            </div>
                                            <div className="text-xs text-secondary dark:text-gray-400">
                                                {edge.packet_ids?.length || 0} packets
                                            </div>
                                        </div>
                                        {edge.rationale && (
                                            <div className="mt-1 text-xs text-tertiary dark:text-gray-500">
                                                {edge.rationale}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {((roundRoutingGraph.unmatched_need_ids?.length || 0) > 0 || (roundRoutingGraph.unmatched_packet_ids?.length || 0) > 0) && (
                        <div className="rounded-md border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
                            unmatched needs: {roundRoutingGraph.unmatched_need_ids?.length || 0} · unmatched packets: {roundRoutingGraph.unmatched_packet_ids?.length || 0}
                        </div>
                    )}
                </div>
            )}

            {session.ended_at && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Ended
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {formatLocalDateTime(session.ended_at)}
                    </div>
                </div>
            )}

            <MemoryImpactGraphPanel
                workspaceId={workspaceId}
                apiUrl={API_URL}
                sessionId={session.id}
                title="Selected Memory Subgraph"
                description="This session view makes the selected packet, produced decisions, action items, and writeback landing visible in one focused graph."
            />

            {canonicalMemory?.memory_item_id && (
                <GovernedMemoryPreview
                    workspaceId={workspaceId}
                    memoryItemId={canonicalMemory.memory_item_id}
                    apiUrl={API_URL}
                    lifecycleStatus={canonicalMemory.lifecycle_status}
                    verificationStatus={canonicalMemory.verification_status}
                />
            )}

            {workflowEvidenceDiagnostics && (
                <div className="rounded-lg border border-default dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-4 space-y-3">
                    <WorkflowEvidenceSummary
                        label="Workflow Evidence Packet"
                        profile={workflowEvidenceDiagnostics.profile}
                        scope={workflowEvidenceDiagnostics.scope}
                        selectedLineCount={workflowEvidenceDiagnostics.selected_line_count}
                        totalLineBudget={workflowEvidenceDiagnostics.total_line_budget}
                        totalCandidateCount={workflowEvidenceDiagnostics.total_candidate_count}
                        totalDroppedCount={workflowEvidenceDiagnostics.total_dropped_count}
                        renderedSectionCount={workflowEvidenceDiagnostics.rendered_section_count}
                        budgetUtilizationRatio={workflowEvidenceDiagnostics.budget_utilization_ratio}
                    />

                    <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Rendered Sections
                            </div>
                            <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                {workflowEvidenceDiagnostics.rendered_section_count || 0}
                            </div>
                        </div>
                        <div className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2">
                            <div className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Rendered
                            </div>
                            <div className="mt-1 text-sm text-primary dark:text-gray-100">
                                {workflowEvidenceDiagnostics.rendered ? 'yes' : 'no'}
                            </div>
                        </div>
                    </div>

                    {workflowEvidenceSections.length > 0 && (
                        <div className="space-y-2">
                            <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                                Section Selection
                            </label>
                            <div className="space-y-2">
                                {workflowEvidenceSections.map((section) => (
                                    <div
                                        key={section.title}
                                        className="rounded-md bg-surface-secondary dark:bg-gray-800 px-3 py-2"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="text-sm text-primary dark:text-gray-100">
                                                {formatWorkflowEvidenceLabel(section.title)}
                                            </div>
                                            <div className="text-xs text-secondary dark:text-gray-400">
                                                selected {section.selectedCount} of {section.candidateCount}
                                            </div>
                                        </div>
                                        <div className="mt-1 text-xs text-tertiary dark:text-gray-500">
                                            section limit {section.limit} · dropped {section.droppedCount}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Agenda */}
            {agenda.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Agenda
                    </label>
                    <ul className="mt-1 space-y-1">
                        {agenda.map((item, i) => (
                            <li key={i} className="text-sm text-primary dark:text-gray-200 flex items-start gap-2">
                                <span className="text-xs text-tertiary mt-0.5">{i + 1}.</span>
                                <span>{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Minutes */}
            {session.minutes_md && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Minutes
                    </label>
                    <div className="mt-1 p-3 bg-surface-secondary dark:bg-gray-800 rounded text-sm text-primary dark:text-gray-200 whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">
                        {session.minutes_md}
                    </div>
                </div>
            )}

            {/* Action Items */}
            {actionItems.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Action Items ({actionItems.length})
                    </label>
                    <div className="mt-1 space-y-2">
                        {actionItems.map((item, i) => (
                            <div
                                key={i}
                                className="flex items-start gap-2 p-2 bg-surface-secondary dark:bg-gray-800 rounded"
                            >
                                <span className={`text-xs mt-0.5 ${item.status === 'done' ? 'text-green-600' : 'text-secondary'
                                    }`}>
                                    {item.status === 'done' ? 'Done' : 'Open'}
                                </span>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm text-primary dark:text-gray-200">
                                        {item.description || JSON.stringify(item)}
                                    </div>
                                    {item.assignee && (
                                        <div className="text-xs text-tertiary dark:text-gray-500 mt-0.5">
                                            → {item.assignee}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Decisions */}
            {decisions.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Decisions ({decisions.length})
                    </label>
                    <div className="mt-1 space-y-1">
                        {decisions.map((d, i) => (
                            <div key={i} className="text-xs text-primary dark:text-gray-300 p-1.5 bg-surface-secondary dark:bg-gray-800 rounded font-mono truncate">
                                {d}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="rounded-lg border border-default dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                            {t('meetingsScenePatchLabel')}
                        </label>
                        <div className="mt-1 text-sm text-primary dark:text-gray-100">
                            {t('meetingsScenePatchDescription')}
                        </div>
                    </div>
                    <button
                        onClick={() => setShowScenePatchPanel((current) => !current)}
                        className="rounded-lg border border-default dark:border-gray-600 px-3 py-1.5 text-xs text-secondary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                    >
                        {showScenePatchPanel ? t('meetingsScenePatchCollapse') : t('meetingsScenePatchExpand')}
                    </button>
                </div>
                {showScenePatchPanel && (
                    <div className="pt-1">
                        <ScenePatchConsole
                            description={t('meetingsScenePatchConsoleDescription')}
                            patchMode="editable"
                            patchJson={scenePatchJson}
                            onPatchJsonChange={setScenePatchJson}
                            patchError={parsedScenePatch.error}
                            summary={scenePatchSummary}
                            sceneId={patchSceneId}
                            onSceneIdChange={setPatchSceneId}
                            onClearPatch={() => {
                                setScenePatchJson('');
                                setPatchSceneId('');
                                setArtifactId('');
                                setScenePatchResult(null);
                            }}
                            pdAction={{
                                sessionId: session.id,
                                onSessionIdChange: () => undefined,
                                sessionIdReadOnly: true,
                                artifactId,
                                onArtifactIdChange: setArtifactId,
                                applying: applyingScenePatch,
                                result: scenePatchResultView,
                                onApply: applyScenePatch,
                                buttonLabel: t('meetingsScenePatchApplyButton'),
                                description: t('meetingsScenePatchApplyDescription'),
                            }}
                        />
                    </div>
                )}
            </div>

            {/* Navigate to conversation */}
            <button
                onClick={() => {
                    const params = new URLSearchParams();
                    if (session.project_id) params.set('project_id', session.project_id);
                    params.set('meeting', '1');
                    params.set('meeting_session_id', session.id);
                    router.push(`/workspaces/${workspaceId}?${params.toString()}`);
                }}
                className="w-full px-4 py-2 bg-sky-600 dark:bg-sky-700 text-white text-sm rounded-lg hover:bg-sky-700 dark:hover:bg-sky-600 transition-colors"
            >
                Open Conversation
            </button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function MeetingWorkbenchPage() {
    const params = useParams();
    const searchParams = useSearchParams();
    const router = useRouter();
    const workspaceId = params?.workspaceId as string;
    const projectId = searchParams?.get('project_id') || null;
    const sessionId = searchParams?.get('session_id') || null;
    const openScenePatch = searchParams?.get('open_patch') === '1';

    const [sessions, setSessions] = useState<MeetingSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedSession, setSelectedSession] = useState<MeetingSession | null>(null);

    const loadSessions = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const qs = projectId ? `?project_id=${projectId}&limit=50` : '?limit=50';
            const resp = await fetch(
                `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions${qs}`
            );
            if (!resp.ok) throw new Error(`Failed: ${resp.statusText}`);
            const data = await resp.json();
            setSessions(data.sessions || []);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to load sessions');
        } finally {
            setLoading(false);
        }
    }, [projectId, workspaceId]);

    const updateSessionQuery = useCallback(
        (nextSessionId: string | null) => {
            const params = new URLSearchParams(searchParams?.toString() || '');
            if (nextSessionId) {
                params.set('session_id', nextSessionId);
            } else {
                params.delete('session_id');
            }
            const query = params.toString();
            router.replace(
                `/workspaces/${workspaceId}/meetings${query ? `?${query}` : ''}`
            );
        },
        [router, searchParams, workspaceId]
    );

    const handleSelectSession = useCallback(
        async (session: MeetingSession) => {
            try {
                const resp = await fetch(
                    `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions/${session.id}`
                );
                if (resp.ok) {
                    const full = await resp.json();
                    setSelectedSession(full);
                } else {
                    setSelectedSession(session);
                }
            } catch {
                setSelectedSession(session);
            }
            updateSessionQuery(session.id);
        },
        [updateSessionQuery, workspaceId]
    );

    // Load sessions
    useEffect(() => {
        void loadSessions();
    }, [loadSessions]);

    useEffect(() => {
        if (!workspaceId) {
            return;
        }

        const unsubscribe = subscribeEventStream(workspaceId, {
            apiUrl: API_URL,
            eventTypes: ['meeting_start', 'meeting_end', 'compile_job_updated', 'round_routing_graph', 'round_routing_warning'],
            projectId: projectId || undefined,
            onEvent: (event) => {
                void loadSessions();

                const targetSessionId =
                    (event.payload as any)?.session_id ||
                    (event.payload as any)?.meeting_session_id ||
                    (event.metadata as any)?.session_id ||
                    (event.metadata as any)?.meeting_session_id ||
                    null;
                const currentSessionId = selectedSession?.id || sessionId;

                if (!currentSessionId || !targetSessionId || currentSessionId !== targetSessionId) {
                    return;
                }

                fetch(
                    `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions/${targetSessionId}`
                )
                    .then((resp) => (resp.ok ? resp.json() : null))
                    .then((data) => {
                        if (data) {
                            setSelectedSession(data);
                        }
                    })
                    .catch(() => { });
            },
        });

        return unsubscribe;
    }, [loadSessions, projectId, selectedSession?.id, sessionId, workspaceId]);

    useEffect(() => {
        if (!sessionId || loading) {
            return;
        }
        if (selectedSession?.id === sessionId) {
            return;
        }
        const matchedSession = sessions.find((session) => session.id === sessionId);
        if (matchedSession) {
            void handleSelectSession(matchedSession);
        }
    }, [handleSelectSession, loading, selectedSession?.id, sessionId, sessions]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-secondary dark:text-gray-400">Loading meeting sessions…</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-red-500 dark:text-red-400">Error: {error}</div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-primary dark:text-gray-100">
                        Meeting Records
                    </h1>
                    <p className="text-sm text-secondary dark:text-gray-400 mt-1">
                        Session history, decisions, and action items
                    </p>
                </div>
                <button
                    onClick={() => router.push(`/workspaces/${workspaceId}`)}
                    className="px-3 py-1.5 text-sm text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 border border-default dark:border-gray-600 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                >
                    ← Back
                </button>
            </div>

            {/* Main content */}
            <div className="flex-1 overflow-hidden flex">
                {/* Session list */}
                <div className="flex-1 overflow-y-auto p-6">
                    {sessions.length === 0 ? (
                        <div className="text-center py-16">
                            <div className="text-lg font-medium text-primary dark:text-gray-300 mb-1">
                                No meeting records yet
                            </div>
                            <div className="text-sm text-secondary dark:text-gray-400">
                                Persistent Meeting history will appear here once it is enabled for this workspace.
                            </div>
                        </div>
                    ) : (
                        <div className="relative">
                            {/* Timeline line */}
                            <div className="absolute left-[23px] top-0 bottom-0 w-0.5 bg-default dark:bg-gray-700" />

                            {/* Session items */}
                            <div className="space-y-3">
                                {sessions.map((session) => (
                                    <SessionCard
                                        key={session.id}
                                        session={session}
                                        isSelected={selectedSession?.id === session.id}
                                        onClick={() => handleSelectSession(session)}
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Detail panel */}
                {selectedSession && (
                    <div className="w-[400px] border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 overflow-y-auto">
                        <SessionDetail
                            session={selectedSession}
                            workspaceId={workspaceId}
                            autoOpenScenePatch={openScenePatch}
                            onClose={() => {
                                setSelectedSession(null);
                                updateSessionQuery(null);
                            }}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
