'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useT } from '@/lib/i18n';
import { List, AlertCircle, UserCheck, AtSign, Clock } from 'lucide-react';
import PendingTasksPanel from '@/app/workspaces/components/PendingTasksPanel';
import { DecisionCard, DecisionCardData } from './DecisionCard';
import {
  subscribeEventStream,
  eventToBlockerCard,
  UnifiedEvent
} from './eventProjector';
import { InputDialog } from './InputDialog';
import { BranchSelectionDialog } from './BranchSelectionDialog';

// IntentCard type definition
export interface IntentCard {
  id: string;
  title: string;
  description?: string;
  status: 'pending_decision' | 'confirmed' | 'rejected';
  priority: 'high' | 'medium' | 'low';
  decisions?: Array<{
    id: string;
    question: string;
    options: string[];
    selectedOption?: string;
  }>;
  createdAt?: string;
}

interface DecisionPanelProps {
  workspaceId: string;
  apiUrl: string;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  workspace?: {
    playbook_auto_execution_config?: Record<string, {
      confidence_threshold?: number;
      auto_execute?: boolean;
    }>;
    owner_user_id?: string;
  };
}

export function DecisionPanel({
  workspaceId,
  apiUrl,
  onViewArtifact,
  onSwitchToOutcomes,
  workspace,
}: DecisionPanelProps) {
  const t = useT();
  const [intentCards, setIntentCards] = useState<IntentCard[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingTaskCount, setPendingTaskCount] = useState(0);

  const [decisionCards, setDecisionCards] = useState<DecisionCardData[]>([]);
  const [events, setEvents] = useState<UnifiedEvent[]>([]);
  const [filter, setFilter] = useState<'all' | 'blockers' | 'assigned-to-me' | 'mentioned-me' | 'waiting-on-others'>('all');
  const [showLegacyTasks, setShowLegacyTasks] = useState(false);
  const [inputDialog, setInputDialog] = useState<{
    title: string;
    fields: Array<{ key: string; label: string; type?: 'text' | 'textarea' | 'file'; required?: boolean; placeholder?: string }>;
    onSubmit: (values: Record<string, string>) => void;
  } | null>(null);
  const [branchDialog, setBranchDialog] = useState<{
    title: string;
    alternatives: Array<{ playbook_code: string; confidence: number; rationale: string; differences?: string[] }>;
    recommendedBranch?: string;
    onSubmit: (selectedPlaybookCode: string) => void;
  } | null>(null);
  const currentUserId = workspace?.owner_user_id || 'default-user';

  const loadIntentCards = React.useCallback(async () => {
    try {
      setLoading(true);
      // Fetch all intents to show both pending decisions and history
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intents`
      );
      if (response.ok) {
        const data = await response.json();
        const cards = (data.intents || []).map((intent: any) => ({
          id: intent.id,
          title: intent.title,
          description: intent.description,
          status: intent.status === 'CANDIDATE' ? 'pending_decision' as const
            : intent.status === 'CONFIRMED' ? 'confirmed' as const
            : 'rejected' as const,
          priority: intent.metadata?.priority || 'medium' as const,
          createdAt: intent.created_at,
        }));
        setIntentCards(cards);
      } else {
        setIntentCards([]);
      }
    } catch (err) {
      console.error('Failed to load intent cards:', err);
      setIntentCards([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, apiUrl]);

  const handleDecisionCardAction = useCallback(async (detail: any) => {
    const { decisionId, actionType, event, payload } = detail;
    try {
      const action = actionType === 'upload' ? 'clarify' : actionType === 'review' ? 'override' : 'confirm';
      const requestBody: any = { action };

      if (actionType === 'upload' && payload.missing_inputs) {
        // Open input dialog to collect missing inputs
        return new Promise<void>((resolve) => {
          setInputDialog({
            title: 'Provide Missing Inputs',
            fields: payload.missing_inputs.map((input: string) => ({
              key: input,
              label: input,
              type: 'text',
              required: true,
              placeholder: `Enter ${input}`
            })),
            onSubmit: async (values) => {
              setInputDialog(null);
              requestBody.providedInputs = values;
              // Continue with the API call
              try {
                const response = await fetch(
                  `${apiUrl}/api/v1/workspaces/${workspaceId}/decision-cards/${decisionId}/confirm`,
                  {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody),
                  }
                );

                if (!response.ok) {
                  const error = await response.json().catch(() => ({}));
                  throw new Error(error.detail || 'Failed to confirm decision');
                }

                // Remove processed card
                setDecisionCards(prev => prev.filter(c => c.id !== decisionId));

                // Trigger refresh
                window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                resolve();
              } catch (err) {
                console.error('Failed to handle decision card action:', err);
                alert(`Operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
                resolve();
              }
            }
          });
        });
      }

      if (actionType === 'review' && payload.clarification_questions) {
        // Open clarification dialog to collect answers
        return new Promise<void>((resolve) => {
          setInputDialog({
            title: 'Clarify Questions',
            fields: payload.clarification_questions.map((q: string, index: number) => ({
              key: `question_${index}`,
              label: q,
              type: 'textarea',
              required: true,
              placeholder: `Answer: ${q}`
            })),
            onSubmit: async (values) => {
              setInputDialog(null);
              // Map back to question -> answer format
              requestBody.clarificationAnswers = payload.clarification_questions.reduce((acc: any, q: string, index: number) => {
                acc[q] = values[`question_${index}`] || '';
                return acc;
              }, {});
              // Continue with the API call
              try {
                const response = await fetch(
                  `${apiUrl}/api/v1/workspaces/${workspaceId}/decision-cards/${decisionId}/confirm`,
                  {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody),
                  }
                );

                if (!response.ok) {
                  const error = await response.json().catch(() => ({}));
                  throw new Error(error.detail || 'Failed to confirm decision');
                }

                // Remove processed card
                setDecisionCards(prev => prev.filter(c => c.id !== decisionId));

                // Trigger refresh
                window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                resolve();
              } catch (err) {
                console.error('Failed to handle decision card action:', err);
                alert(`Operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
                resolve();
              }
            }
          });
        });
      }

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/decision-cards/${decisionId}/confirm`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        }
      );

      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Failed to confirm decision');
      }

      setDecisionCards(prev => prev.filter(c => c.id !== decisionId));
      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
    } catch (err) {
      console.error('Failed to handle decision card action:', err);
      alert(`Operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const unsubscribe = subscribeEventStream(
      workspaceId,
      {
        apiUrl,
        eventTypes: ['decision_required', 'branch_proposed', 'run_state_changed', 'artifact_created'],
        onEvent: (event: UnifiedEvent) => {
          setEvents(prev => {
            if (prev.find(e => e.id === event.id)) {
              return prev;
            }
            return [...prev, event];
          });

          if (event.type === 'decision_required' || event.type === 'branch_proposed') {
            const card = eventToBlockerCard(event);
            if (card) {
              setDecisionCards(prev => {
                if (prev.find(c => c.id === card.id)) {
                  return prev.map(c => c.id === card.id ? card : c);
                }
                return [...prev, card];
              });
            }
          }

          if (event.type === 'run_state_changed' && event.payload.new_state === 'DONE') {
            setDecisionCards(prev => prev.filter(c =>
              c.status !== 'DONE' && c.status !== 'REJECTED'
            ));
          }
        },
        onError: (error) => {
          console.error('Event stream error:', error);
        },
      }
    );

    const handleCardAction = (e: any) => {
      handleDecisionCardAction(e.detail);
    };
    window.addEventListener('decision-card-action', handleCardAction);

    const handleBranchSelection = (e: any) => {
      const { alternatives, recommendedBranch } = e.detail;
      setBranchDialog({
        title: 'Select Execution Plan',
        alternatives,
        recommendedBranch,
        onSubmit: async (selectedPlaybookCode: string) => {
          setBranchDialog(null);
          try {
            const response = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/decision-cards/${e.detail.branchId}/confirm`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  action: 'override',
                  overridePlaybookCode: selectedPlaybookCode,
                  overrideReason: 'User selected from multiple candidate plans',
                }),
              }
            );

            if (!response.ok) {
              const error = await response.json().catch(() => ({}));
              throw new Error(error.detail || 'Failed to select branch');
            }

            setDecisionCards(prev => prev.filter(c => c.id !== e.detail.branchId));
            window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
          } catch (err) {
            console.error('Failed to select branch:', err);
            alert(`Operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
          }
        },
      });
    };
    window.addEventListener('branch-selection', handleBranchSelection);

    return () => {
      unsubscribe();
      window.removeEventListener('decision-card-action', handleCardAction);
      window.removeEventListener('branch-selection', handleBranchSelection);
    };
  }, [workspaceId, handleDecisionCardAction]);

  useEffect(() => {
    const loadInitialEvents = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=decision_required,branch_proposed&limit=50`
        );
        if (response.ok) {
          const data = await response.json();
          const initialEvents = data.events || [];
          setEvents(initialEvents);

          const cards = initialEvents
            .map((e: UnifiedEvent) => eventToBlockerCard(e))
            .filter((c: DecisionCardData | null): c is DecisionCardData => c !== null);
          setDecisionCards(cards);
        }
      } catch (err) {
        console.error('Failed to load initial events:', err);
      }
    };

    loadInitialEvents();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    // Load intent cards on mount and when workspaceId/apiUrl changes
    loadIntentCards();

    const handleWorkspaceUpdate = () => {
      loadIntentCards();
    };

    const handleTaskUpdate = () => {
      loadIntentCards();
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        loadIntentCards();
      }
    };

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleTaskUpdate);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleTaskUpdate);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [workspaceId, apiUrl, loadIntentCards]);

  const pendingCards = intentCards.filter(c => c.status === 'pending_decision');
  const historyCards = intentCards.filter(c => c.status !== 'pending_decision');
  const highPriorityCount = pendingCards.filter(c => c.priority === 'high').length;

  const sortedDecisionCards = useMemo(() => {
    return [...decisionCards].sort((a, b) => {
      if (a.priority === 'blocker' && b.priority !== 'blocker') return -1;
      if (a.priority !== 'blocker' && b.priority === 'blocker') return 1;

      const aIsMine = a.assignee === currentUserId;
      const bIsMine = b.assignee === currentUserId;
      if (aIsMine && !bIsMine) return -1;
      if (!aIsMine && bIsMine) return 1;
      if (a.dueAt && b.dueAt) {
        return a.dueAt.getTime() - b.dueAt.getTime();
      }
      if (a.dueAt && !b.dueAt) return -1;
      if (!a.dueAt && b.dueAt) return 1;

      return 0;
    });
  }, [decisionCards, currentUserId]);

  const filteredDecisionCards = useMemo(() => {
    switch (filter) {
      case 'blockers':
        return sortedDecisionCards.filter(c => c.priority === 'blocker' && c.status === 'OPEN');
      case 'assigned-to-me':
        return sortedDecisionCards.filter(c => c.assignee === currentUserId && c.status === 'OPEN');
      case 'mentioned-me':
        return sortedDecisionCards.filter(c => c.watchers?.includes(currentUserId) && c.status === 'OPEN');
      case 'waiting-on-others':
        return sortedDecisionCards.filter(c => c.assignee && c.assignee !== currentUserId && c.status === 'OPEN');
      default:
        return sortedDecisionCards.filter(c => c.status === 'OPEN' || c.status === 'NEED_INFO');
    }
  }, [sortedDecisionCards, filter, currentUserId]);

  const blockerCount = useMemo(() => {
    return decisionCards.filter(c => c.priority === 'blocker' && c.status === 'OPEN').length;
  }, [decisionCards]);

  const assignedToMeCount = useMemo(() => {
    return decisionCards.filter(c => c.assignee === currentUserId && c.status === 'OPEN').length;
  }, [decisionCards, currentUserId]);

  const totalPending = pendingTaskCount + pendingCards.length + filteredDecisionCards.length;

  return (
    <div className="decision-panel flex-1 flex flex-col overflow-hidden">
      {/* Panel Header */}
      <div className={`section-header decision-section-header ${blockerCount > 0 ? 'has-high-priority' : ''} px-3 py-2 bg-surface dark:bg-gray-800 border-b dark:border-gray-700`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold">Pending Decisions</span>
            {filteredDecisionCards.length > 0 && (
              <span className="badge pending text-xs px-1.5 py-0.5 rounded bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300">
                {filteredDecisionCards.length}
              </span>
            )}
            {blockerCount > 0 && (
              <span
                className="badge high-priority text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300"
                title={`${blockerCount} blocker${blockerCount !== 1 ? 's' : ''}`}
              >
                {blockerCount}
              </span>
            )}
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-1 overflow-x-auto">
          {[
            {
              id: 'all',
              label: 'All',
              icon: List,
              count: decisionCards.filter(c => c.status === 'OPEN' || c.status === 'NEED_INFO').length
            },
            {
              id: 'blockers',
              label: 'Blockers',
              icon: AlertCircle,
              count: blockerCount
            },
            {
              id: 'assigned-to-me',
              label: 'Assigned to Me',
              icon: UserCheck,
              count: assignedToMeCount
            },
            {
              id: 'mentioned-me',
              label: 'Mentioned Me',
              icon: AtSign,
              count: decisionCards.filter(c => c.watchers?.includes(currentUserId) && c.status === 'OPEN').length
            },
            {
              id: 'waiting-on-others',
              label: 'Waiting on Others',
              icon: Clock,
              count: decisionCards.filter(c => c.assignee && c.assignee !== currentUserId && c.status === 'OPEN').length
            },
          ].map(option => {
            const Icon = option.icon;
            const isActive = filter === option.id;
            return (
              <button
                key={option.id}
                onClick={() => setFilter(option.id as any)}
                className={`relative flex items-center justify-center gap-1.5 px-2 py-1.5 rounded transition-all ${
                  isActive
                    ? 'bg-accent dark:bg-blue-700 text-white'
                    : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-600'
                }`}
                title={!isActive ? `${option.label}${option.count > 0 ? ` (${option.count})` : ''}` : undefined}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                {isActive && (
                  <span className="text-xs font-medium whitespace-nowrap">
                    {option.label}
                  </span>
                )}
                {option.count > 0 && (
                  <span className={`absolute -top-1 -right-1 min-w-[14px] h-[14px] px-1 text-[10px] leading-none flex items-center justify-center rounded-full ${
                    isActive
                      ? 'bg-surface-accent text-accent dark:text-blue-700'
                      : 'bg-red-500 text-white'
                  }`}>
                    {option.count > 99 ? '99+' : option.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Decision Content */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-3">
        {/* Unified Decision Cards (from event stream) */}
        {filteredDecisionCards.length > 0 ? (
          <div className="space-y-3">
            {filteredDecisionCards.map(card => (
              <DecisionCard
                key={card.id}
                card={card}
                currentUserId={currentUserId}
                onExpand={(cardId) => {
                  console.log('Expand card:', cardId);
                }}
              />
            ))}
          </div>
        ) : (
          !loading && (
            <div className="text-xs text-tertiary dark:text-gray-500 italic py-4 text-center">
              No pending decisions
            </div>
          )
        )}

        {(pendingCards.length > 0 || pendingTaskCount > 0) && (
          <div className="mt-4 pt-4 border-t border-default dark:border-gray-700">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-secondary dark:text-gray-400">
                Legacy Tasks - Will be migrated to unified decisions
              </div>
              <button
                onClick={() => setShowLegacyTasks(!showLegacyTasks)}
                className="text-[10px] text-tertiary dark:text-gray-500 hover:text-secondary dark:hover:text-gray-400"
              >
                {showLegacyTasks ? 'Hide' : 'Show'}
              </button>
            </div>

            {showLegacyTasks && (
              <>
                {/* Legacy Pending Tasks */}
                {pendingTaskCount > 0 && (
                  <div className="mb-4">
                    <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                      Tasks requiring human confirmation / input
                    </div>
                    <PendingTasksPanel
                      workspaceId={workspaceId}
                      apiUrl={apiUrl}
                      onViewArtifact={onViewArtifact}
                      onSwitchToOutcomes={onSwitchToOutcomes}
                      workspace={workspace}
                      onTaskCountChange={setPendingTaskCount}
                    />
                  </div>
                )}

                {/* Legacy Intent Cards */}
                {pendingCards.length > 0 && (
                  <div>
                    <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                      Intent Card
                    </div>
                    <div className="space-y-2">
                      {pendingCards.map(card => (
                        <IntentCardItem
                          key={card.id}
                          card={card}
                          workspaceId={workspaceId}
                          apiUrl={apiUrl}
                          onStatusChange={loadIntentCards}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* History Section */}
        {historyCards.length > 0 && (
          <div className="history-intents border-t border-default dark:border-gray-700 pt-3">
            <button
              className="flex items-center gap-2 text-xs text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-300 transition-colors"
              onClick={() => setShowHistory(!showHistory)}
            >
              <span className="chevron">{showHistory ? '▼' : '▶'}</span>
              <span>History ({historyCards.length})</span>
            </button>

            {showHistory && (
              <div className="history-list mt-2 space-y-2">
                {historyCards.map(card => (
                  <IntentCardItem
                    key={card.id}
                    card={card}
                    collapsed
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    onStatusChange={loadIntentCards}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Dialog */}
      {inputDialog && (
        <InputDialog
          title={inputDialog.title}
          fields={inputDialog.fields}
          onSubmit={inputDialog.onSubmit}
          onCancel={() => setInputDialog(null)}
        />
      )}

      {/* Branch Selection Dialog */}
      {branchDialog && (
        <BranchSelectionDialog
          title={branchDialog.title}
          alternatives={branchDialog.alternatives}
          recommendedBranch={branchDialog.recommendedBranch}
          onSubmit={branchDialog.onSubmit}
          onCancel={() => setBranchDialog(null)}
        />
      )}
    </div>
  );
}

function IntentCardItem({
  card,
  collapsed,
  workspaceId,
  apiUrl,
  onStatusChange,
}: {
  card: IntentCard;
  collapsed?: boolean;
  workspaceId: string;
  apiUrl: string;
  onStatusChange?: () => void;
}) {
  const [isProcessing, setIsProcessing] = useState(false);

  const handleConfirm = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/intents/${card.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'CONFIRMED' }),
      });
      if (response.ok) {
        onStatusChange?.();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } else {
        const error = await response.json().catch(() => ({}));
        console.error('Failed to confirm intent:', error);
        alert(`Failed to confirm intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('Failed to confirm intent:', err);
      alert(`Failed to confirm intent: ${err.message || 'Unknown error'}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReject = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/intents/${card.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'REJECTED' }),
      });
      if (response.ok) {
        onStatusChange?.();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } else {
        const error = await response.json().catch(() => ({}));
        console.error('Failed to reject intent:', error);
        alert(`Failed to reject intent: ${error.detail || 'Unknown error'}`);
      }
    } catch (err: any) {
      console.error('Failed to reject intent:', err);
      alert(`Failed to reject intent: ${err.message || 'Unknown error'}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className={`intent-card-item border rounded p-2 ${
      card.priority === 'high'
        ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
        : card.priority === 'medium'
        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
        : 'bg-surface dark:bg-gray-800 border-default dark:border-gray-700'
    } ${collapsed ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-primary dark:text-gray-100">
          {card.title}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
          card.priority === 'high'
            ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300'
            : card.priority === 'medium'
            ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
            : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
        }`}>
          {card.priority === 'high' ? 'High' : card.priority === 'medium' ? 'Medium' : 'Low'}
        </span>
      </div>
      {!collapsed && card.description && (
        <div className="text-xs text-secondary dark:text-gray-400 mt-1">
          {card.description}
        </div>
      )}
      {!collapsed && card.status === 'pending_decision' && (
        <div className="flex items-center gap-1.5 mt-2">
          <button
            onClick={handleConfirm}
            disabled={isProcessing}
            className={`flex-1 px-2 py-1 text-xs font-medium rounded transition-all ${
              isProcessing
                ? 'bg-gray-400 dark:bg-gray-600 text-white cursor-not-allowed opacity-75'
                : 'bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100 hover:bg-surface-secondary dark:hover:bg-gray-700 border border-default dark:border-gray-600'
            }`}
          >
            {isProcessing ? (
              <>
                <div className="w-3 h-3 border-2 border-secondary dark:border-gray-300 border-t-transparent rounded-full animate-spin mx-auto"></div>
              </>
            ) : (
              'Confirm'
            )}
          </button>
          <button
            onClick={handleReject}
            disabled={isProcessing}
            className={`px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 border border-red-300 dark:border-red-700 rounded hover:bg-red-50 dark:hover:bg-red-900/30 transition-all flex items-center justify-center gap-1 flex-shrink-0 ${
              isProcessing ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <span>✕</span>
            <span>Reject</span>
          </button>
        </div>
      )}
    </div>
  );
}

