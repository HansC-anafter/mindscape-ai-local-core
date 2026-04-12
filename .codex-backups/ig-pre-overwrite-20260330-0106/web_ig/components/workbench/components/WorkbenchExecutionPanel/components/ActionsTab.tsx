/**
 * Actions Tab containing Generate Content, Batch Processor, Complete Workflow,
 * Content Validation, Export Package, and Publish sections
 */
import React from 'react';
import {
    Activity,
    CheckSquare,
    Download,
    RefreshCw,
    Sparkles,
    Upload,
} from 'lucide-react';
import type { BatchActionType, BatchScopeType, PostStatusType, WorkflowPresetType } from '../types';

interface ActionsTabProps {
    // Post state
    selectedPostId: string | null;
    selectedPostPath: string | null;
    filteredPostPaths: string[];
    isRunning: boolean;

    // Batch state
    batchAction: BatchActionType;
    setBatchAction: (action: BatchActionType) => void;
    batchScope: BatchScopeType;
    setBatchScope: (scope: BatchScopeType) => void;
    batchManualPostPaths: string;
    setBatchManualPostPaths: (paths: string) => void;
    batchStrictMode: boolean;
    setBatchStrictMode: (strict: boolean) => void;
    batchOutputFolder: string;
    setBatchOutputFolder: (folder: string) => void;
    batchNewStatus: PostStatusType;
    setBatchNewStatus: (status: PostStatusType) => void;
    batchOperationsText: string;
    setBatchOperationsText: (text: string) => void;
    batchOperationConfigText: string;
    setBatchOperationConfigText: (text: string) => void;
    batchNotice: string | null;

    // Workflow state
    workflowPreset: WorkflowPresetType;
    setWorkflowPreset: (preset: WorkflowPresetType) => void;
    workflowTargetFolder: string;
    setWorkflowTargetFolder: (folder: string) => void;
    workflowPostContent: string;
    setWorkflowPostContent: (content: string) => void;
    workflowPostMetadataText: string;
    setWorkflowPostMetadataText: (text: string) => void;
    workflowStepsText: string;
    setWorkflowStepsText: (text: string) => void;
    workflowInitialContextText: string;
    setWorkflowInitialContextText: (text: string) => void;
    workflowReviewNotesText: string;
    setWorkflowReviewNotesText: (text: string) => void;
    workflowNotice: string | null;

    // Actions
    onRunPlaybook: (playbookCode: string, additionalInputs?: any) => Promise<{ success: boolean; execution_id?: string; error?: string }>;
    runBatchProcessor: () => Promise<void>;
    runCompleteWorkflow: () => Promise<void>;
}

export function ActionsTab({
    selectedPostId,
    selectedPostPath,
    filteredPostPaths,
    isRunning,
    batchAction,
    setBatchAction,
    batchScope,
    setBatchScope,
    batchManualPostPaths,
    setBatchManualPostPaths,
    batchStrictMode,
    setBatchStrictMode,
    batchOutputFolder,
    setBatchOutputFolder,
    batchNewStatus,
    setBatchNewStatus,
    batchOperationsText,
    setBatchOperationsText,
    batchOperationConfigText,
    setBatchOperationConfigText,
    batchNotice,
    workflowPreset,
    setWorkflowPreset,
    workflowTargetFolder,
    setWorkflowTargetFolder,
    workflowPostContent,
    setWorkflowPostContent,
    workflowPostMetadataText,
    setWorkflowPostMetadataText,
    workflowStepsText,
    setWorkflowStepsText,
    workflowInitialContextText,
    setWorkflowInitialContextText,
    workflowReviewNotesText,
    setWorkflowReviewNotesText,
    workflowNotice,
    onRunPlaybook,
    runBatchProcessor,
    runCompleteWorkflow,
}: ActionsTabProps) {
    return (
        <div className="space-y-2">
            {/* Generate Content */}
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    Generate Content
                </h5>
                <div className="space-y-1.5">
                    <button
                        onClick={() => onRunPlaybook('ig_post_generation')}
                        disabled={isRunning}
                        className="w-full px-3 py-2 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        <Sparkles className="w-3.5 h-3.5" />
                        Generate Post
                    </button>
                </div>
            </div>

            {/* Batch Processor */}
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    Batch Processor
                </h5>
                <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">action</div>
                            <select
                                value={batchAction}
                                onChange={(e) => setBatchAction(e.target.value as BatchActionType)}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                            >
                                <option value="batch_validate">batch_validate</option>
                                <option value="batch_generate_export_packs">batch_generate_export_packs</option>
                                <option value="batch_update_status">batch_update_status</option>
                                <option value="batch_process">batch_process</option>
                            </select>
                        </div>
                        <div>
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">scope</div>
                            <select
                                value={batchScope}
                                onChange={(e) => setBatchScope(e.target.value as BatchScopeType)}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                            >
                                <option value="filtered">filtered ({filteredPostPaths.length})</option>
                                <option value="selected" disabled={!selectedPostId}>selected</option>
                                <option value="manual">manual</option>
                            </select>
                        </div>
                    </div>

                    {batchScope === 'manual' && (
                        <textarea
                            value={batchManualPostPaths}
                            onChange={(e) => setBatchManualPostPaths(e.target.value)}
                            rows={4}
                            className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                            placeholder="post_paths (one per line)"
                        />
                    )}

                    <label className="flex items-center gap-2 text-xs text-blue-900 dark:text-blue-100">
                        <input
                            type="checkbox"
                            checked={batchStrictMode}
                            onChange={(e) => setBatchStrictMode(e.target.checked)}
                            className="rounded"
                        />
                        strict_mode
                    </label>

                    {batchAction === 'batch_generate_export_packs' && (
                        <div>
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">output_folder</div>
                            <input
                                value={batchOutputFolder}
                                onChange={(e) => setBatchOutputFolder(e.target.value)}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                            />
                        </div>
                    )}

                    {batchAction === 'batch_update_status' && (
                        <div>
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">new_status</div>
                            <select
                                value={batchNewStatus}
                                onChange={(e) => setBatchNewStatus(e.target.value as PostStatusType)}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                            >
                                <option value="draft">draft</option>
                                <option value="review">review</option>
                                <option value="ready">ready</option>
                                <option value="scheduled">scheduled</option>
                                <option value="published">published</option>
                                <option value="measured">measured</option>
                                <option value="archived">archived</option>
                            </select>
                        </div>
                    )}

                    {batchAction === 'batch_process' && (
                        <>
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">operations (one per line)</div>
                                <textarea
                                    value={batchOperationsText}
                                    onChange={(e) => setBatchOperationsText(e.target.value)}
                                    rows={3}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                                />
                            </div>
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">operation_config (JSON)</div>
                                <textarea
                                    value={batchOperationConfigText}
                                    onChange={(e) => setBatchOperationConfigText(e.target.value)}
                                    rows={3}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 font-mono"
                                />
                            </div>
                        </>
                    )}

                    <button
                        onClick={() => void runBatchProcessor()}
                        disabled={isRunning}
                        className="w-full px-3 py-2 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Run Batch
                    </button>
                    {batchNotice && <div className="text-[10px] text-blue-900 dark:text-blue-100">{batchNotice}</div>}
                </div>
            </div>

            {/* Complete Workflow */}
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    Complete Workflow
                </h5>
                <div className="space-y-2">
                    <div>
                        <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">preset</div>
                        <select
                            value={workflowPreset}
                            onChange={(e) => setWorkflowPreset(e.target.value as WorkflowPresetType)}
                            className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                        >
                            <option value="create_post_workflow">create_post_workflow</option>
                            <option value="review_workflow">review_workflow</option>
                            <option value="execute_workflow">execute_workflow</option>
                        </select>
                    </div>

                    {workflowPreset === 'create_post_workflow' && (
                        <>
                            <textarea
                                value={workflowPostContent}
                                onChange={(e) => setWorkflowPostContent(e.target.value)}
                                rows={4}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                                placeholder="post_content"
                            />
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">target_folder</div>
                                <input
                                    value={workflowTargetFolder}
                                    onChange={(e) => setWorkflowTargetFolder(e.target.value)}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800"
                                />
                            </div>
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">post_metadata (JSON)</div>
                                <textarea
                                    value={workflowPostMetadataText}
                                    onChange={(e) => setWorkflowPostMetadataText(e.target.value)}
                                    rows={3}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 font-mono"
                                />
                            </div>
                        </>
                    )}

                    {workflowPreset === 'review_workflow' && (
                        <div>
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">review_notes (JSON)</div>
                            <textarea
                                value={workflowReviewNotesText}
                                onChange={(e) => setWorkflowReviewNotesText(e.target.value)}
                                rows={3}
                                className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 font-mono"
                            />
                            <div className="text-[10px] text-blue-900 dark:text-blue-100 mt-1">
                                Uses selected post_path: {selectedPostPath || '—'}
                            </div>
                        </div>
                    )}

                    {workflowPreset === 'execute_workflow' && (
                        <>
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">workflow_steps (JSON)</div>
                                <textarea
                                    value={workflowStepsText}
                                    onChange={(e) => setWorkflowStepsText(e.target.value)}
                                    rows={4}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 font-mono"
                                />
                            </div>
                            <div>
                                <div className="text-[10px] text-blue-900 dark:text-blue-100 mb-1">initial_context (JSON)</div>
                                <textarea
                                    value={workflowInitialContextText}
                                    onChange={(e) => setWorkflowInitialContextText(e.target.value)}
                                    rows={3}
                                    className="w-full px-2 py-1 text-xs rounded border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 font-mono"
                                />
                            </div>
                        </>
                    )}

                    <button
                        onClick={() => void runCompleteWorkflow()}
                        disabled={isRunning}
                        className="w-full px-3 py-2 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Run Workflow
                    </button>
                    {workflowNotice && <div className="text-[10px] text-blue-900 dark:text-blue-100">{workflowNotice}</div>}
                </div>
            </div>

            {/* Content Validation */}
            <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
                    Content Validation
                </h5>
                <div className="space-y-1.5">
                    <button
                        onClick={async () => {
                            await onRunPlaybook('ig_content_checker');
                        }}
                        disabled={isRunning}
                        className="w-full px-3 py-2 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50 flex items-center justify-center gap-2"
                        title={!selectedPostId ? 'Please select a post first' : 'Check content compliance of selected post'}
                    >
                        <CheckSquare className="w-3.5 h-3.5" />
                        Content Check
                    </button>
                    <button
                        onClick={async () => {
                            await onRunPlaybook('ig_frontmatter_validator');
                        }}
                        disabled={isRunning}
                        className="w-full px-3 py-2 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-50 flex items-center justify-center gap-2"
                        title={!selectedPostId ? 'Please select a post first' : 'Validate frontmatter and calculate readiness score'}
                    >
                        <Activity className="w-3.5 h-3.5" />
                        Ready Score
                    </button>
                </div>
            </div>

            {/* Export Package */}
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-green-900 dark:text-green-100 mb-2">
                    Export Package
                </h5>
                <button
                    onClick={() => onRunPlaybook('ig_export_pack_generator')}
                    disabled={isRunning}
                    className="w-full px-3 py-2 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                    title={!selectedPostId ? 'Please select a post first' : 'Generate export pack for selected post'}
                >
                    <Download className="w-3.5 h-3.5" />
                    Export Pack
                </button>
            </div>

            {/* Publish / Schedule */}
            <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-red-900 dark:text-red-100 mb-2">
                    Publish / Schedule
                </h5>
                <button
                    onClick={() => onRunPlaybook('ig_publish_content')}
                    disabled={isRunning}
                    className="w-full px-3 py-2 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 flex items-center justify-center gap-2"
                    title={!selectedPostId ? 'Please select a post first' : 'Publish selected post to Instagram (account configuration required)'}
                >
                    <Upload className="w-3.5 h-3.5" />
                    Publish
                </button>
            </div>
        </div>
    );
}
