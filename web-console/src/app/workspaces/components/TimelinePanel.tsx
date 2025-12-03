'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { t } from '@/lib/i18n';
import OCRQualityIndicator from '@/components/ocr/OCRQualityIndicator';
import StoragePathConfigModal from '@/components/StoragePathConfigModal';
import RunningTimelineItem from './RunningTimelineItem';
import PendingTimelineItem from './PendingTimelineItem';
import ArchivedTimelineItem from './ArchivedTimelineItem';
import ExecutionInspector from './ExecutionInspector';
import OutcomesPanel from '../[workspaceId]/components/OutcomesPanel';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';

// Fade-in blink animation styles
const fadeInBlinkStyle = `
  @keyframes fadeInBlink {
    0% {
      opacity: 0;
      transform: translateY(8px);
    }
    20% {
      opacity: 1;
      transform: translateY(0);
    }
    40% {
      opacity: 0.7;
    }
    60% {
      opacity: 1;
    }
    80% {
      opacity: 0.8;
    }
    100% {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes fadeOut {
    0% {
      opacity: 1;
      transform: translateY(0);
      max-height: 500px;
    }
    100% {
      opacity: 0;
      transform: translateY(-10px);
      max-height: 0;
      margin-bottom: 0;
      padding-top: 0;
      padding-bottom: 0;
    }
  }
`;

interface TimelineItem {
  id: string;
  workspace_id: string;
  message_id?: string;
  task_id?: string;
  type: string;
  title: string;
  summary?: string;
  data?: any;
  cta?: {
    action: string;
    label: string;
    confirm?: boolean;
  } | Array<{
    action: string;
    label: string;
    confirm?: boolean;
  }>;
  created_at: string;
  // Execution context fields (if timeline item is from Playbook execution)
  execution_id?: string;
  task_status?: string;
  task_started_at?: string;
  task_completed_at?: string;
  has_execution_context?: boolean;
}

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  steps?: ExecutionStep[];
  [key: string]: any;
}

interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  requires_confirmation: boolean;
  confirmation_status?: string;
  [key: string]: any;
}

interface TimelinePanelProps {
  workspaceId: string;
  apiUrl: string;
  isInSettingsPage?: boolean;
  focusExecutionId?: string | null;
  onClearFocus?: () => void;
  showArchivedOnly?: boolean;
  onArtifactClick?: (artifact: any) => void;
}

export default function TimelinePanel({
  workspaceId,
  apiUrl,
  isInSettingsPage = false,
  focusExecutionId = null,
  onClearFocus,
  showArchivedOnly = false,
  onArtifactClick
}: TimelinePanelProps) {
  // Use context data if available (when inside WorkspaceDataProvider)
  const contextData = useWorkspaceDataOptional();

  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [localExecutions, setLocalExecutions] = useState<ExecutionSession[]>([]);
  const [executionSteps, setExecutionSteps] = useState<Map<string, ExecutionStep[]>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null);
  const timelineScrollContainerRef = useRef<HTMLDivElement>(null);
  const [showStorageConfigModal, setShowStorageConfigModal] = useState(false);
  const [localWorkspace, setLocalWorkspace] = useState<any>(null);
  const [retryTimelineItemId, setRetryTimelineItemId] = useState<string | null>(null);
  // Track which items have been shown (for fade-in animation)
  const [visibleItemIds, setVisibleItemIds] = useState<Set<string>>(new Set());
  const previousItemsRef = useRef<TimelineItem[]>([]);
  // Track collapsed/expanded state for execution sections
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  // Use context data if available, otherwise use local state
  const executions = contextData?.executions || localExecutions;
  const workspace = contextData?.workspace || localWorkspace;

  // Build executionSteps map from context data if available
  const contextExecutionSteps = useMemo(() => {
    if (!contextData?.executions) return null;
    const stepsMap = new Map<string, ExecutionStep[]>();
    for (const exec of contextData.executions) {
      if (exec.steps && exec.steps.length > 0) {
        stepsMap.set(exec.execution_id, exec.steps);
      }
    }
    return stepsMap;
  }, [contextData?.executions]);

  // Use context steps if available
  const effectiveExecutionSteps = contextExecutionSteps || executionSteps;

  // Handle execution click - emit event to parent to show ExecutionInspector in main area
  const handleExecutionClick = (executionId: string) => {
    window.dispatchEvent(new CustomEvent('open-execution-inspector', {
      detail: { executionId, workspaceId }
    }));
  };

  // Track if initial load has been done to prevent duplicate loads
  const hasLoadedRef = useRef<string | null>(null);

  useEffect(() => {
    // Only load timeline items once per workspaceId (timeline items are not in context yet)
    if (hasLoadedRef.current !== workspaceId) {
      loadTimelineItems();
      hasLoadedRef.current = workspaceId;
    }

    // Only load executions and workspace if not using context
    if (!contextData) {
      loadExecutions();
      loadWorkspace();
    }

    // Event handling is done by context when available
    if (contextData) {
      return; // Context handles event-based refresh
    }

    // Fallback: local event handling when not using context
    let debounceTimer: NodeJS.Timeout | null = null;
    let isPending = false;

    const handleChatUpdate = () => {
      if (process.env.NODE_ENV === 'development') {
        console.log('TimelinePanel: Received workspace-chat-updated event, scheduling refresh');
      }
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isPending) {
          isPending = true;
          Promise.all([loadTimelineItems(), loadExecutions()]).finally(() => {
            isPending = false;
          });
        }
      }, 1000);
    };

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
    };
  }, [workspaceId]); // Remove contextData from dependencies to prevent re-loading

  // Expose loadTimelineItems for manual refresh
  useEffect(() => {
    // Store loadTimelineItems in window for debugging
    (window as any).__timelinePanelRefresh = loadTimelineItems;
  }, []);

  const isFirstLoadRef = useRef(true);

  useEffect(() => {
    if (timelineItems.length > 0 && !loading) {
      if (isFirstLoadRef.current) {
        const scrollTimer = setTimeout(() => {
          if (timelineScrollContainerRef.current) {
            timelineScrollContainerRef.current.scrollTop = 0;
          }
        }, 300);
        isFirstLoadRef.current = false;
        return () => clearTimeout(scrollTimer);
      } else {
        // Always scroll to top when new items are added (not first load)
        // This ensures latest tasks are visible at the top
        const scrollTimer = setTimeout(() => {
          if (timelineScrollContainerRef.current) {
            timelineScrollContainerRef.current.scrollTop = 0;
          }
        }, 100);
        return () => clearTimeout(scrollTimer);
      }
    }
  }, [timelineItems, loading]);

  const loadWorkspace = async () => {
    // Skip if using context data
    if (contextData) return;

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
      if (response.ok) {
        const workspaceData = await response.json();
        setLocalWorkspace(workspaceData);
      }
    } catch (err) {
      console.error('Failed to load workspace:', err);
    }
  };

  const loadExecutions = async () => {
    // Skip if using context data
    if (contextData) return;

    try {
      // Use batch API to get executions with steps in a single request
      // This avoids N+1 queries - steps are included for active executions only
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/executions-with-steps?limit=100&include_steps_for=active`
      );
      if (!response.ok) {
        throw new Error(`Failed to load executions: ${response.status}`);
      }

      const data = await response.json();
      const executionsList: ExecutionSession[] = data.executions || [];
      setLocalExecutions(executionsList);

      // Extract steps from the batch response (steps are already included in each execution)
      const stepsMap = new Map<string, ExecutionStep[]>();
      for (const execution of executionsList) {
        if (execution.steps && execution.steps.length > 0) {
          stepsMap.set(execution.execution_id, execution.steps);
        }
      }
      setExecutionSteps(stepsMap);
    } catch (err: any) {
      console.error('Failed to load executions:', err);
      // Don't set error state - executions are optional
    }
  };

  const loadTimelineItems = async () => {
    try {
      setLoading(true);
      setError(null);
      if (process.env.NODE_ENV === 'development') {
        console.log(`TimelinePanel: Loading timeline items for workspace ${workspaceId}`);
      }
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline?limit=50`
      );

      if (!response.ok) {
        throw new Error(`Failed to load timeline: ${response.status}`);
      }

      const data = await response.json();
      if (process.env.NODE_ENV === 'development') {
        console.log(`TimelinePanel: Received data:`, data);
        console.log(`TimelinePanel: timeline_items count: ${data.timeline_items?.length || 0}`);
        console.log(`TimelinePanel: events count: ${data.events?.length || 0}`);
      }

      // Use timeline_items (primary) or events (backward compatibility)
      // timeline_items are the result cards from Pack executions
      const items = data.timeline_items || data.events || [];
      if (process.env.NODE_ENV === 'development') {
        console.log(`TimelinePanel: Setting ${items.length} timeline items`);
      }

      // Identify new items (not in previous list)
      const previousIds = new Set(previousItemsRef.current.map((item: TimelineItem) => item.id));
      const newItems = items.filter((item: TimelineItem) => !previousIds.has(item.id));

      // Update previous items ref
      previousItemsRef.current = items;

      // Set all items immediately (no global loading state for refresh)
      setTimelineItems(items);

      // Animate new items one by one with fade-in and blink effect
      if (newItems.length > 0) {
        // Mark existing items as visible immediately
        const existingIds = items.filter((item: TimelineItem) => previousIds.has(item.id)).map((item: TimelineItem) => item.id);
        setVisibleItemIds(prev => new Set([...Array.from(prev), ...existingIds]));

        // Animate new items with stagger
        newItems.forEach((item: TimelineItem, index: number) => {
          setTimeout(() => {
            setVisibleItemIds(prev => new Set([...Array.from(prev), item.id]));
          }, index * 150); // Stagger animation: 150ms between each item
        });
      } else {
        // If no new items, mark all existing items as visible
        setVisibleItemIds(new Set(items.map((item: TimelineItem) => item.id)));
      }

      if (isFirstLoadRef.current) {
        setTimeout(() => {
          if (timelineScrollContainerRef.current) {
            timelineScrollContainerRef.current.scrollTop = 0;
          }
        }, 200);
      }
    } catch (err: any) {
      console.error('Failed to load timeline items:', err);
      setError(err.message || 'Failed to load timeline');
    } finally {
      setLoading(false);
    }
  };

  const handleCTAAction = async (item: TimelineItem, action: string, ctaItem?: { confirm?: boolean }) => {
    // Handle view_result action locally - just expand/collapse the item
    if (action === 'view_result') {
      setExpandedItemId(expandedItemId === item.id ? null : item.id);
      return;
    }

    // CTA actions removed - Timeline items are completed, no actions needed
    // All items in Timeline are already executed
    console.log('CTA action called but Timeline items are completed - no action needed');
  };

  const getTypeLabel = (type: string): string => {
    const typeLabels: Record<string, string> = {
      'INTENT_SEEDS': 'Intent Seeds',
      'PLAN': 'Plan',
      'SUMMARY': 'Summary',
      'DRAFT': 'Draft',
      'ERROR': 'Error',
      'SUGGESTION': 'Suggestion',
      'OCR_RESULT': 'OCR Result',
      'DOCUMENT_PROCESSING': 'Document Processing',
    };
    return typeLabels[type] || type;
  };

  const getTypeColor = (type: string): string => {
    const typeColors: Record<string, string> = {
      'INTENT_SEEDS': 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700',
      'PLAN': 'bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 border-gray-400 dark:border-gray-600',
      'SUMMARY': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700',
      'DRAFT': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700',
      'ERROR': 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700',
      'SUGGESTION': 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600',
    };
    return typeColors[type] || 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600';
  };

  // Only show loading on initial load, not on refresh
  if (loading && timelineItems.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-2 pt-2">
          <div className="text-xs text-gray-500 dark:text-gray-300">Loading...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto px-2 pt-2">
          <div className="text-xs text-red-600 dark:text-red-400">{error}</div>
          <button
            onClick={loadTimelineItems}
            className="mt-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const handleStorageConfigSuccess = async () => {
    // Reload workspace to get updated storage path
    await loadWorkspace();

    // If we have a timeline item ID to retry, automatically retry
    if (retryTimelineItemId) {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline-items/${retryTimelineItemId}/retry-artifact`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          }
        );
        if (response.ok) {
          const result = await response.json();
          if (result.success) {
            // Trigger workspace-chat-updated event to refresh all components including this one
            // The event handler will debounce and handle the refresh, avoiding duplicate calls
            window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
            setRetryTimelineItemId(null);
          } else {
            alert(`${t('configSaved')}, ${t('retryFailed')}: ${result.error || t('unknownError')}`);
          }
        } else {
          const error = await response.json();
          alert(`${t('configSaved')}, ${t('retryFailed')}: ${error.detail || t('unknownError')}`);
        }
      } catch (err: any) {
        alert(`${t('configSaved')}, ${t('retryFailed')}: ${err.message || t('unknownError')}`);
      }
    }

    // Close the modal after successful configuration
    setShowStorageConfigModal(false);
    setRetryTimelineItemId(null);
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: fadeInBlinkStyle }} />
      <StoragePathConfigModal
        isOpen={showStorageConfigModal}
        onClose={() => {
          setShowStorageConfigModal(false);
          setRetryTimelineItemId(null);
        }}
        workspace={workspace}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onSuccess={handleStorageConfigSuccess}
      />
      <div className="flex flex-col h-full">
        {/* Timeline content - scrollable */}
        <div
          ref={timelineScrollContainerRef}
          data-timeline-container
          className="flex-1 overflow-y-auto px-2 pt-2"
        >
        {/* Execution Sessions - Three Sections or Focus Mode */}
        {(() => {
          const now = new Date();
          const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

          // Get current step for each execution to check requires_confirmation
          const getCurrentStep = (execution: ExecutionSession): ExecutionStep | null => {
            const steps = effectiveExecutionSteps.get(execution.execution_id) || [];
            return steps.find(s => s.step_index === execution.current_step_index) || null;
          };

          // Focus mode: Group executions by playbook
          if (focusExecutionId) {
            const focusedExecution = executions.find(e => e.execution_id === focusExecutionId);
            if (!focusedExecution) {
              // Focused execution not found, fall through to normal view
              // Don't return null, let it continue to normal mode rendering below
            } else {
              const focusedPlaybookCode = focusedExecution.playbook_code;

            // Current execution
            const currentExecution = focusedExecution;

            // Same playbook other executions
            const samePlaybookExecutions = executions
              .filter(e => e.execution_id !== focusExecutionId && e.playbook_code === focusedPlaybookCode)
              .sort((a, b) => {
                const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
                const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
                return bTime - aTime;
              });

            // Other playbooks executions
            const otherPlaybookExecutions = executions
              .filter(e => e.playbook_code !== focusedPlaybookCode)
              .sort((a, b) => {
                const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
                const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
                return bTime - aTime;
              });

            return (
              <div className="space-y-4">
                {/* Return to Workspace Overview Button */}
                {onClearFocus && (
                  <div className="px-2 pb-2 border-b dark:border-gray-700">
                    <button
                      onClick={() => {
                        // Clear focus and dispatch event to ensure all components are notified
                        onClearFocus();
                        window.dispatchEvent(new CustomEvent('clear-execution-focus'));
                      }}
                      className="w-full px-3 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                      </svg>
                      {t('returnToWorkspaceOverview')}
                    </button>
                  </div>
                )}

                {/* Current Execution */}
                <div>
                    <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 px-2">
                      {t('currentExecution')}
                    </h3>
                  <RunningTimelineItem
                    execution={currentExecution}
                    currentStep={getCurrentStep(currentExecution)}
                    onClick={() => handleExecutionClick(currentExecution.execution_id)}
                    apiUrl={apiUrl}
                    workspaceId={workspaceId}
                  />
                </div>

                {/* Same Playbook Other Executions */}
                {samePlaybookExecutions.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 px-2">
                      {t('otherExecutionsOfSamePlaybook')}
                    </h3>
                    <div className="space-y-2">
                      {samePlaybookExecutions.map((execution) => {
                        const currentStep = getCurrentStep(execution);
                        if (execution.status === 'running' && execution.paused_at && currentStep?.requires_confirmation && currentStep.confirmation_status === 'pending') {
                          return (
                            <PendingTimelineItem
                              key={execution.execution_id}
                              execution={execution}
                              currentStep={currentStep}
                              onClick={() => handleExecutionClick(execution.execution_id)}
                              apiUrl={apiUrl}
                              workspaceId={workspaceId}
                            />
                          );
                        } else if (execution.status === 'running') {
                          return (
                            <RunningTimelineItem
                              key={execution.execution_id}
                              execution={execution}
                              currentStep={currentStep}
                              onClick={() => handleExecutionClick(execution.execution_id)}
                              apiUrl={apiUrl}
                              workspaceId={workspaceId}
                            />
                          );
                        } else {
                          return (
                            <ArchivedTimelineItem
                              key={execution.execution_id}
                              execution={execution}
                              onClick={() => handleExecutionClick(execution.execution_id)}
                            />
                          );
                        }
                      })}
                    </div>
                  </div>
                )}

                {/* Other Playbooks Executions (Collapsible) */}
                {otherPlaybookExecutions.length > 0 && (
                  <div>
                    <button
                      onClick={() => {
                        const key = 'other_playbooks';
                        setCollapsedSections(prev => {
                          const next = new Set(prev);
                          if (next.has(key)) {
                            next.delete(key);
                          } else {
                            next.add(key);
                          }
                          return next;
                        });
                      }}
                      className="w-full px-2 py-2 text-xs font-semibold text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg transition-colors flex items-center justify-between"
                    >
                      <span>{t('otherPlaybooksExecutions')}</span>
                      <svg
                        className={`w-4 h-4 transition-transform ${collapsedSections.has('other_playbooks') ? '' : 'rotate-180'}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {!collapsedSections.has('other_playbooks') && (
                      <div className="space-y-2 mt-2">
                        {otherPlaybookExecutions.map((execution) => {
                          const currentStep = getCurrentStep(execution);
                          if (execution.status === 'running' && execution.paused_at && currentStep?.requires_confirmation && currentStep.confirmation_status === 'pending') {
                            return (
                              <PendingTimelineItem
                                key={execution.execution_id}
                                execution={execution}
                                currentStep={currentStep}
                                onClick={() => handleExecutionClick(execution.execution_id)}
                                apiUrl={apiUrl}
                                workspaceId={workspaceId}
                              />
                            );
                          } else if (execution.status === 'running') {
                            return (
                              <RunningTimelineItem
                                key={execution.execution_id}
                                execution={execution}
                                currentStep={currentStep}
                                onClick={() => handleExecutionClick(execution.execution_id)}
                                apiUrl={apiUrl}
                                workspaceId={workspaceId}
                              />
                            );
                          } else {
                            return (
                              <ArchivedTimelineItem
                                key={execution.execution_id}
                                execution={execution}
                                onClick={() => handleExecutionClick(execution.execution_id)}
                              />
                            );
                          }
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
            }
          }

          // Normal mode: Three sections (Running / Pending Confirmation / Archived)

          // Pending confirmation executions (status = "running" AND paused_at IS NOT NULL AND requires_confirmation = true)
          // These are executions that are waiting for user confirmation before continuing
          const pendingConfirmationExecutions = executions
            .filter(exec => {
              if (exec.status !== 'running') return false;
              if (!exec.paused_at) return false;
              const currentStep = getCurrentStep(exec);
              return currentStep?.requires_confirmation && currentStep.confirmation_status === 'pending';
            })
            .sort((a, b) => {
              const aTime = a.paused_at ? new Date(a.paused_at).getTime() : 0;
              const bTime = b.paused_at ? new Date(b.paused_at).getTime() : 0;
              return bTime - aTime; // Newest first
            });

          // Running executions (status = "running" AND NOT paused with confirmation required)
          // These are executions that are actively processing (not waiting for confirmation)
          // IMPORTANT: Exclude any executions that are in pendingConfirmationExecutions to avoid duplicates
          const pendingConfirmationExecutionIds = new Set(pendingConfirmationExecutions.map(e => e.execution_id));
          const runningExecutions = executions
            .filter(exec => {
              if (exec.status !== 'running') return false;
              // Exclude if already in pending confirmation list
              if (pendingConfirmationExecutionIds.has(exec.execution_id)) return false;
              const currentStep = getCurrentStep(exec);
              // Only include if NOT paused with pending confirmation
              return !(exec.paused_at && currentStep?.requires_confirmation && currentStep.confirmation_status === 'pending');
            })
            .sort((a, b) => {
              const aTime = a.started_at ? new Date(a.started_at).getTime() : 0;
              const bTime = b.started_at ? new Date(b.started_at).getTime() : 0;
              return bTime - aTime; // Newest first
            });

          // Archived executions (status IN ("succeeded", "failed") AND created_at < 1 hour ago)
          const archivedExecutions = executions
            .filter(exec => {
              if (!['succeeded', 'failed'].includes(exec.status)) return false;
              if (!exec.created_at) return false;
              const createdAt = new Date(exec.created_at);
              return createdAt < oneHourAgo;
            })
            .sort((a, b) => {
              const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
              const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
              return bTime - aTime; // Newest first
            });

          const toggleSection = (section: string) => {
            setCollapsedSections(prev => {
              const newSet = new Set(prev);
              if (newSet.has(section)) {
                newSet.delete(section);
              } else {
                newSet.add(section);
              }
              return newSet;
            });
          };

          const isSectionCollapsed = (section: string) => collapsedSections.has(section);

          // If showArchivedOnly is true, only show archived section
          if (showArchivedOnly) {
            return (
              <div className="space-y-1">
                <div
                  className="text-xs font-semibold text-gray-500 dark:text-gray-300 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-1"
                  onClick={() => toggleSection('archived')}
                >
                  <span className="select-none">{isSectionCollapsed('archived') ? '▶' : '▼'}</span>
                  <span>{t('timelineArchived')} {archivedExecutions.length > 0 && `(${archivedExecutions.length})`}</span>
                </div>
                {!isSectionCollapsed('archived') && (
                  archivedExecutions.length > 0 ? (
                    archivedExecutions.map((execution) => (
                      <ArchivedTimelineItem
                        key={execution.execution_id}
                        execution={execution}
                        onOpenConsole={() => handleExecutionClick(execution.execution_id)}
                      />
                    ))
                  ) : (
                    <div className="text-xs text-gray-400 dark:text-gray-300 px-1 py-2 opacity-60">
                      {t('noArchivedExecutions')}
                    </div>
                  )
                )}
              </div>
            );
          }

          return (
            <div className="space-y-4">
              {/* Running Section - Always show, even if empty, with collapse/expand */}
              <div className="space-y-2">
                <div
                  className="text-xs font-semibold text-gray-700 dark:text-gray-300 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-1"
                  onClick={() => toggleSection('running')}
                >
                  <span className="select-none">{isSectionCollapsed('running') ? '▶' : '▼'}</span>
                  <span>{t('timelineRunning')} {runningExecutions.length > 0 && `(${runningExecutions.length})`}</span>
                </div>
                {!isSectionCollapsed('running') && (
                  runningExecutions.length > 0 ? (
                    runningExecutions.map((execution) => {
                      const currentStep = getCurrentStep(execution);
                      return (
                        <RunningTimelineItem
                          key={execution.execution_id}
                          execution={execution}
                          apiUrl={apiUrl}
                          workspaceId={workspaceId}
                          currentStep={currentStep || undefined}
                          onClick={() => {
                            // Open Execution Inspector in main area when clicked
                            handleExecutionClick(execution.execution_id);
                          }}
                          onUpdate={(updatedExecution, updatedStep) => {
                            // Update state when SSE events arrive
                            if (contextData) {
                              // If using context, refresh executions to get latest data
                              if (updatedExecution.status !== execution.status) {
                                contextData.refreshExecutions();
                                // If execution completed, also refresh tasks
                                if (updatedExecution.status === 'succeeded' || updatedExecution.status === 'failed') {
                                  contextData.refreshTasks();
                                }
                              }
                            } else {
                              // If not using context, update local state
                              setLocalExecutions(prev =>
                                prev.map(e =>
                                  e.execution_id === updatedExecution.execution_id
                                    ? updatedExecution
                                    : e
                                )
                              );
                              if (updatedStep) {
                                setExecutionSteps(prev => {
                                  const newMap = new Map(prev);
                                  const existingSteps = newMap.get(execution.execution_id) || [];
                                  const stepIndex = existingSteps.findIndex(s => s.id === updatedStep.id);
                                  if (stepIndex >= 0) {
                                    existingSteps[stepIndex] = updatedStep;
                                  } else {
                                    existingSteps.push(updatedStep);
                                  }
                                  newMap.set(execution.execution_id, existingSteps);
                                  return newMap;
                                });
                              }
                              // Refresh executions if status changed
                              if (updatedExecution.status !== execution.status) {
                                loadExecutions();
                              }
                            }
                          }}
                        />
                      );
                    })
                  ) : (
                    <div className="text-xs text-gray-400 dark:text-gray-300 px-1 py-2">
                      {t('noRunningExecutions')}
                    </div>
                  )
                )}
              </div>

              {/* Pending Confirmation Section - Always show, even if empty, with collapse/expand */}
              <div className="space-y-2">
                <div
                  className="text-xs font-semibold text-amber-700 dark:text-amber-400 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 flex items-center gap-1"
                  onClick={() => toggleSection('pending')}
                >
                  <span className="select-none">{isSectionCollapsed('pending') ? '▶' : '▼'}</span>
                  <span>{t('timelinePendingConfirmation')} {pendingConfirmationExecutions.length > 0 && `(${pendingConfirmationExecutions.length})`}</span>
                </div>
                {!isSectionCollapsed('pending') && (
                  pendingConfirmationExecutions.length > 0 ? (
                    pendingConfirmationExecutions.map((execution) => {
                      const currentStep = getCurrentStep(execution);
                      if (!currentStep) return null;

                      return (
                        <PendingTimelineItem
                          key={execution.execution_id}
                          execution={execution}
                          currentStep={currentStep}
                          apiUrl={apiUrl}
                          workspaceId={workspaceId}
                          onClick={() => handleExecutionClick(execution.execution_id)}
                          onAction={(action) => {
                            // Reload executions after action
                            loadExecutions();
                          }}
                        />
                      );
                    })
                  ) : (
                    <div className="text-xs text-gray-400 dark:text-gray-300 px-1 py-2">
                      {t('noPendingConfirmations')}
                    </div>
                  )
                )}
              </div>

              {/* Outcomes Section - Show OutcomesPanel content in place of Archived */}
              <div className="space-y-1">
                <div className="text-xs font-semibold text-gray-500 dark:text-gray-300 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10">
                  <span>{t('tabOutcomes') || '成果'}</span>
                </div>
                <div className="px-1">
                  <OutcomesPanel
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    onArtifactClick={onArtifactClick}
                  />
                </div>
              </div>
            </div>
          );
        })()}

        {/* Timeline Items (existing) - Show items NOT from Playbook executions */}
        {(() => {
          const now = new Date();
          const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

          // Filter timeline items: exclude those that have execution_id (from Playbook executions)
          const nonExecutionItems = timelineItems.filter((item: TimelineItem) => !item.execution_id);

          // Filter timeline items: exclude those that are from Playbook executions
          const failedExecutions = executions
            .filter(exec => exec.status === 'failed')
            .sort((a, b) => {
              const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
              const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
              return bTime - aTime; // Most recent first
            })
            .slice(0, 5); // Show only last 5 failures

          // Helper function to extract short reason from failure_reason
          const getShortFailureReason = (reason?: string): string => {
            if (!reason) return t('unknownError');
            const lowerReason = reason.toLowerCase();
            if (lowerReason.includes('timeout') || lowerReason.includes('timed out')) {
              return 'Timeout';
            }
            if (lowerReason.includes('tool error') || lowerReason.includes('tool failed')) {
              return 'Tool Error';
            }
            if (lowerReason.includes('validation') || lowerReason.includes('invalid')) {
              return 'Validation Failed';
            }
            if (lowerReason.includes('network') || lowerReason.includes('connection')) {
              return 'Network Error';
            }
            // Return first 30 chars as fallback
            return reason.length > 30 ? reason.substring(0, 30) + '...' : reason;
          };

          // Render non-execution timeline items (DRAFT, SUMMARY, etc.)
          const renderNonExecutionItems = () => {
            if (nonExecutionItems.length === 0) {
              return null;
            }

            return (
              <div className="space-y-1.5 mt-4">
                <div className="text-xs font-semibold text-gray-600 dark:text-gray-300 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10">
                  {t('timelineItems') || 'Timeline Items'}
                </div>
                {nonExecutionItems
                  .sort((a: TimelineItem, b: TimelineItem) => {
                    const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
                    const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
                    return bTime - aTime; // Most recent first
                  })
                  .map((item: TimelineItem) => {
                    const itemType = item.type || 'PLAN';
                    const itemTitle = item.title || 'Untitled';
                    const itemSummary = item.summary || '';

                    return (
                      <div
                        key={item.id}
                        className="w-full text-left bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-sm transition-all"
                        style={{ position: 'relative' }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                              {itemTitle}
                            </div>
                            {itemSummary && (
                            <div className="text-[10px] text-gray-500 dark:text-gray-300 mt-0.5 line-clamp-2">
                              {itemSummary}
                            </div>
                          )}
                          <div className="text-[10px] text-gray-400 dark:text-gray-300 mt-0.5">
                            {itemType}
                          </div>
                        </div>
                        <span className="text-[10px] text-gray-400 dark:text-gray-300 ml-2">
                            {item.created_at
                              ? new Date(item.created_at).toLocaleTimeString(undefined, {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  hour12: true
                                })
                              : ''}
                          </span>
                        </div>
                        {item.cta && Array.isArray(item.cta) && item.cta.length > 0 && (() => {
                          // Filter out Confirm/confirmation buttons if task is already completed
                          const isCompleted = item.task_status === 'succeeded' ||
                                            item.task_status === 'failed' ||
                                            item.task_completed_at !== undefined;

                          const filteredCTAs = item.cta.filter((cta: any) => {
                            // Hide confirmation buttons for completed tasks
                            if (isCompleted) {
                              const action = cta.action?.toLowerCase() || '';
                              const label = cta.label?.toLowerCase() || '';
                              // Filter out confirm/confirmation actions
                              if (action.includes('confirm') ||
                                  action.includes('publish') ||
                                  action.includes('export') ||
                                  action.includes('execute_external') ||
                                  label.includes('confirm') ||
                                  label.includes('确认')) {
                                return false;
                              }
                            }
                            return true;
                          });

                          if (filteredCTAs.length === 0) {
                            return null;
                          }

                          return (
                            <div className="flex items-center gap-1.5 mt-2" style={{ position: 'relative', zIndex: 10 }}>
                              {filteredCTAs.map((ctaItem, idx) => {
                                const handleCTAClick = async (e: React.MouseEvent) => {
                                  e.stopPropagation();
                                  e.preventDefault();

                                if (ctaItem.action === 'view_result' && item.task_id) {
                                  // First try to fetch artifacts (actual files)
                                  try {
                                    const response = await fetch(
                                      `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/by-task/${item.task_id}`
                                    );
                                    if (response.ok) {
                                      const artifactsData = await response.json();
                                      const artifacts = artifactsData.artifacts || artifactsData || [];
                                      if (artifacts && artifacts.length > 0) {
                                        // Open artifact in new window or download
                                        const artifact = artifacts[0];
                                        if (artifact.download_url) {
                                          window.open(artifact.download_url, '_blank');
                                          return;
                                        } else if (artifact.file_path) {
                                          // Try to construct download URL
                                          const downloadUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/download`;
                                          window.open(downloadUrl, '_blank');
                                          return;
                                        }
                                      }
                                    }
                                  } catch (err) {
                                    console.error('Error fetching artifacts:', err);
                                  }

                                  // If no artifacts, format and display the content from item.data
                                  if (item.data) {
                                    let content = '';
                                    const data = item.data;

                                    // Format based on content type
                                    if (data.content) {
                                      // Draft content
                                      content = `# ${data.title || 'Generated Draft'}\n\n`;
                                      if (data.format) {
                                        content += `**Format:** ${data.format}\n\n`;
                                      }
                                      content += data.content;
                                      if (data.tags && data.tags.length > 0) {
                                        content += `\n\n**Tags:** ${data.tags.join(', ')}`;
                                      }
                                    } else if (data.summary !== undefined || item.type === 'SUMMARY') {
                                      // Summary content
                                      content = `# ${data.title || 'Generated Summary'}\n\n`;
                                      if (data.summary && data.summary.trim()) {
                                        content += `## Summary\n\n${data.summary}\n\n`;
                                      }
                                      if (data.key_points && data.key_points.length > 0) {
                                        content += `## Key Points\n\n`;
                                        data.key_points.forEach((point: string, idx: number) => {
                                          content += `${idx + 1}. ${point}\n`;
                                        });
                                        content += '\n';
                                      }
                                      if (data.themes && data.themes.length > 0) {
                                        content += `## Themes\n\n`;
                                        data.themes.forEach((theme: string) => {
                                          content += `- ${theme}\n`;
                                        });
                                      }

                                      // If no content was generated, show a message
                                      if (!data.summary && (!data.key_points || data.key_points.length === 0) && (!data.themes || data.themes.length === 0)) {
                                        content += `\n> **Note:** Summary generation completed, but no content was extracted.\n`;
                                        content += `> This may be because:\n`;
                                        content += `> - No relevant content was found in the input\n`;
                                        content += `> - The content was too short to summarize\n`;
                                        content += `> - Files were not processed (files_processed: ${data.files_processed || 0})\n\n`;
                                        if (data.message) {
                                          content += `**Status:** ${data.message}\n`;
                                        }
                                      }
                                    } else {
                                      // Fallback: show formatted JSON
                                      content = JSON.stringify(data, null, 2);
                                    }

                                    // Create a formatted text file and open it
                                    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
                                    const url = URL.createObjectURL(blob);
                                    window.open(url, '_blank');
                                  } else {
                                    alert('No content available for this task.');
                                  }
                                } else if (ctaItem.action === 'add_to_intents' || ctaItem.action === 'add_to_tasks') {
                                  // These actions are for suggestion items, not completed timeline items
                                  console.log('Action not applicable for completed timeline item:', ctaItem.action);
                                } else {
                                  // Handle other actions
                                  await handleCTAAction(item, ctaItem.action, ctaItem);
                                }
                              };

                              const isPrimary = ctaItem.action === 'view_result' || ctaItem.label?.includes('查看') || ctaItem.label?.includes('View');
                              const isConfirm = ctaItem.action?.includes('confirm') || ctaItem.label?.includes('Confirm') || ctaItem.label?.includes('确认');

                              // If it's a confirm button and task is completed, show as status badge (not clickable)
                              if (isConfirm && isCompleted) {
                                return (
                                  <span
                                    key={idx}
                                    className="text-[10px] px-2 py-0.5 rounded font-medium bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-700"
                                  >
                                    {ctaItem.label || ctaItem.action}
                                  </span>
                                );
                              }

                              return (
                                <button
                                  key={idx}
                                  type="button"
                                  onClick={handleCTAClick}
                                  onMouseDown={(e) => e.stopPropagation()}
                                  className={`text-[10px] px-2 py-0.5 rounded font-medium transition-colors cursor-pointer ${
                                    isPrimary
                                      ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-700 hover:bg-blue-100 dark:hover:bg-blue-900/40'
                                      : 'bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                                  }`}
                                  style={{ pointerEvents: 'auto', zIndex: 10 }}
                                >
                                  {ctaItem.label || ctaItem.action}
                                </button>
                              );
                            })}
                            </div>
                          );
                        })()}
                      </div>
                    );
                  })}
              </div>
            );
          };

          if (failedExecutions.length === 0 && nonExecutionItems.length === 0) {
            return null;
          }

          return (
            <>
              {renderNonExecutionItems()}
              {failedExecutions.length > 0 && (
                <div className="space-y-1.5 mt-4">
                <div className="text-xs font-semibold text-gray-600 dark:text-gray-300 px-1 py-1 sticky top-0 bg-white dark:bg-gray-900 z-10">
                  {t('recentFailures')}
                </div>
                  {failedExecutions.map((execution) => {
                    const shortReason = getShortFailureReason(execution.failure_reason);
                    const runNumber = execution.execution_id?.slice(-8) || 'N/A';

                    return (
                      <button
                        key={execution.execution_id}
                        onClick={() => handleExecutionClick(execution.execution_id)}
                        className="w-full text-left bg-white dark:bg-gray-800 border border-red-200 dark:border-red-800 rounded p-2 hover:border-red-300 dark:hover:border-red-700 hover:shadow-sm transition-all"
                      >
                        {/* Playbook name + Run # */}
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                              {execution.playbook_code || 'Unknown Playbook'}
                            </div>
                            <div className="text-[10px] text-gray-500 dark:text-gray-300 mt-0.5">
                              Run #{runNumber}
                            </div>
                          </div>
                          <span className="text-[10px] text-gray-400 dark:text-gray-300 ml-2">
                            {execution.created_at
                              ? new Date(execution.created_at).toLocaleTimeString(undefined, {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  hour12: true
                                })
                              : ''}
                          </span>
                        </div>
                        {/* Short reason */}
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-700 font-medium">
                            {shortReason}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          );
        })()}

      </div>
    </div>
    </>
  );
}
