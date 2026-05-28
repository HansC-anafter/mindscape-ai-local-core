'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useT } from '@/lib/i18n';
import { formatLocalDateTime } from '@/lib/time';
import { GovernedMemoryPreview } from '../../../../components/workspace/governance/GovernedMemoryPreview';
import { MemoryImpactGraphPanel } from '../../../../components/workspace/governance/MemoryImpactGraphPanel';
import { WorkflowEvidenceSummary } from '../../../../components/workspace/meeting/WorkflowEvidenceSummary';
import {
    buildScenePatchFailureText,
    ScenePatchConsole,
    buildScenePatchSummary,
    parseScenePatchJson,
    type ScenePatchStatusMessage,
} from '../../../../components/workspace/ScenePatchConsole';
import { MEETING_RECORDS_API_URL } from './meetingRecordsApi';
import type {
    CanonicalMemoryLink,
    MeetingSession,
    WorkflowEvidenceDiagnostics,
} from './meetingRecords.types';
import {
    formatWorkflowEvidenceLabel,
    getMeetingRecordStatusStyle,
} from './meetingRecordsUtils';
import {
    applyMeetingScenePatchObjectAction,
    getMeetingScenePatchObjectActionDisabledReason,
} from './meetingScenePatchObjectAction';

interface MeetingSessionDetailPanelProps {
    session: MeetingSession;
    workspaceId: string;
    autoOpenScenePatch?: boolean;
    onClose: () => void;
}

export function MeetingSessionDetailPanel({
    session,
    workspaceId,
    autoOpenScenePatch = false,
    onClose,
}: MeetingSessionDetailPanelProps) {
    const router = useRouter();
    const t = useT();
    const [showScenePatchPanel, setShowScenePatchPanel] = useState(autoOpenScenePatch);
    const [scenePatchJson, setScenePatchJson] = useState('');
    const [patchSceneId, setPatchSceneId] = useState('');
    const [artifactId, setArtifactId] = useState('');
    const [applyingScenePatch, setApplyingScenePatch] = useState(false);
    const [scenePatchResult, setScenePatchResult] = useState<ScenePatchStatusMessage | null>(null);
    const actionItems = session.action_items || [];
    const decisions = session.decisions || [];
    const agenda = session.agenda || [];
    const canonicalMemory = session.metadata?.canonical_memory as CanonicalMemoryLink | undefined;
    const workflowEvidenceDiagnostics =
        session.metadata?.workflow_evidence_diagnostics as WorkflowEvidenceDiagnostics | undefined;
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
                section.limit > 0,
        );

    const parsedScenePatch = useMemo(
        () => parseScenePatchJson(scenePatchJson),
        [scenePatchJson],
    );

    const scenePatchSummary = useMemo(
        () => buildScenePatchSummary(parsedScenePatch.patch, patchSceneId),
        [parsedScenePatch.patch, patchSceneId],
    );
    const scenePatchDisabledReason = useMemo(() => {
        if (!parsedScenePatch.patch) {
            return parsedScenePatch.error
                ? t('meetingsScenePatchParseFailed', { error: parsedScenePatch.error })
                : t('meetingsScenePatchJsonRequired');
        }
        if (!patchSceneId.trim()) {
            return t('meetingsScenePatchSceneIdRequired');
        }
        return getMeetingScenePatchObjectActionDisabledReason(session, workspaceId, patchSceneId);
    }, [parsedScenePatch.error, parsedScenePatch.patch, patchSceneId, session, t, workspaceId]);

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
            setScenePatchResult({
                tone: 'error',
                message: parsedScenePatch.error
                    ? t('meetingsScenePatchParseFailed', { error: parsedScenePatch.error })
                    : t('meetingsScenePatchJsonRequired'),
            });
            return;
        }
        if (!patchSceneId.trim()) {
            setScenePatchResult({
                tone: 'error',
                message: t('meetingsScenePatchSceneIdRequired'),
            });
            return;
        }
        try {
            setApplyingScenePatch(true);
            setScenePatchResult(null);
            const result = await applyMeetingScenePatchObjectAction({
                apiUrl: MEETING_RECORDS_API_URL,
                workspaceId,
                session,
                sceneId: patchSceneId.trim(),
                artifactId,
                storyboardScenePatch: parsedScenePatch.patch,
            });
            setScenePatchResult(result);
        } catch (error) {
            setScenePatchResult({
                tone: 'error',
                message: buildScenePatchFailureText(error),
            });
        } finally {
            setApplyingScenePatch(false);
        }
    }, [artifactId, parsedScenePatch.error, parsedScenePatch.patch, patchSceneId, session, t, workspaceId]);

    return (
        <div className="p-5 space-y-5">
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

            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Status
                    </label>
                    <div className="mt-1">
                        <span className={`text-xs px-2 py-1 rounded ${getMeetingRecordStatusStyle(session.status)}`}>
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
                apiUrl={MEETING_RECORDS_API_URL}
                sessionId={session.id}
                title="Selected Memory Subgraph"
                description="This session view makes the selected packet, produced decisions, action items, and writeback landing visible in one focused graph."
            />

            {canonicalMemory?.memory_item_id && (
                <GovernedMemoryPreview
                    workspaceId={workspaceId}
                    memoryItemId={canonicalMemory.memory_item_id}
                    apiUrl={MEETING_RECORDS_API_URL}
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

            {decisions.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Decisions ({decisions.length})
                    </label>
                    <div className="mt-1 space-y-1">
                        {decisions.map((decision, i) => (
                            <div key={i} className="text-xs text-primary dark:text-gray-300 p-1.5 bg-surface-secondary dark:bg-gray-800 rounded font-mono truncate">
                                {decision}
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
                            objectAction={{
                                id: 'meeting-scene-patch-object-action',
                                title: t('meetingsScenePatchApplyButton'),
                                applying: applyingScenePatch,
                                result: scenePatchResult,
                                onApply: applyScenePatch,
                                buttonLabel: t('meetingsScenePatchApplyButton'),
                                description: t('meetingsScenePatchApplyDescription'),
                                disabled: Boolean(scenePatchDisabledReason),
                                disabledReason: scenePatchDisabledReason,
                                fields: [
                                    {
                                        kind: 'text',
                                        id: 'meeting-session-id',
                                        label: 'meeting_id',
                                        value: session.id,
                                        readOnly: true,
                                    },
                                    {
                                        kind: 'text',
                                        id: 'artifact-id',
                                        label: 'artifact_id（可留空）',
                                        value: artifactId,
                                        onChange: setArtifactId,
                                        placeholder: '留空時由 owner pack 選擇 storyboard artifact',
                                    },
                                ],
                            }}
                        />
                    </div>
                )}
            </div>

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
