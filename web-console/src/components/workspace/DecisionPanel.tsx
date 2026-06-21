'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import type { DecisionCardData } from './DecisionCard';
import {
  subscribeEventStream,
  eventToBlockerCard,
  type UnifiedEvent
} from './eventProjector';
import { DecisionPanelView } from './decisionPanel/DecisionPanelView';
import {
  countAssignedToMeCards,
  countBlockerCards,
  countMentionedMeCards,
  countOpenDecisionCards,
  countWaitingOnOthersCards,
  filterDecisionCards,
  getHistoryIntentCards,
  getPendingIntentCards,
  sortDecisionCards,
} from './decisionPanel/decisionFilters';
import {
  emptyRelatedDecisionContext,
  getRelatedDecisionContextFromEvents,
  getRelatedDecisionContextFromMeetingPayload,
} from './decisionPanel/relatedDecisionContext';
import type {
  BranchDialogState,
  DecisionFilter,
  DecisionPanelProps,
  InputDialogState,
  IntentCard,
  RelatedDecisionContext,
} from './decisionPanel/types';

export type { IntentCard } from './decisionPanel/types';

export function DecisionPanel({
  workspaceId,
  apiUrl,
  selectedThreadId,
  onViewArtifact,
  onSwitchToOutcomes,
  workspace,
}: DecisionPanelProps) {
  const [intentCards, setIntentCards] = useState<IntentCard[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingTaskCount, setPendingTaskCount] = useState(0);

  const [decisionCards, setDecisionCards] = useState<DecisionCardData[]>([]);
  const [, setEvents] = useState<UnifiedEvent[]>([]);
  const [filter, setFilter] = useState<DecisionFilter>('all');
  const [showLegacyTasks, setShowLegacyTasks] = useState(false);
  const [relatedContext, setRelatedContext] = useState<RelatedDecisionContext>(emptyRelatedDecisionContext);
  const [relatedMemoryLoading, setRelatedMemoryLoading] = useState(false);
  const [inputDialog, setInputDialog] = useState<InputDialogState | null>(null);
  const [branchDialog, setBranchDialog] = useState<BranchDialogState | null>(null);
  const currentUserId = workspace?.owner_user_id || 'default-user';

  const loadIntentCards = useCallback(async () => {
    try {
      setLoading(true);
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
          priority: (intent.metadata?.priority || 'medium') as IntentCard['priority'],
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
    const { decisionId, actionType, payload } = detail;
    try {
      const action = actionType === 'upload' ? 'clarify' : actionType === 'review' ? 'override' : 'confirm';
      const requestBody: any = { action };

      if (actionType === 'upload' && payload.missing_inputs) {
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

                setDecisionCards(prev => prev.filter(card => card.id !== decisionId));
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
              requestBody.clarificationAnswers = payload.clarification_questions.reduce((acc: any, q: string, index: number) => {
                acc[q] = values[`question_${index}`] || '';
                return acc;
              }, {});
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

                setDecisionCards(prev => prev.filter(card => card.id !== decisionId));
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

      setDecisionCards(prev => prev.filter(card => card.id !== decisionId));
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
        eventTypes: ['decision_required', 'branch_proposed', 'run_state_changed', 'artifact_created', 'meeting_start'],
        onEvent: (event: UnifiedEvent) => {
          setEvents(prev => {
            if (prev.find(item => item.id === event.id)) {
              return prev;
            }
            return [...prev, event];
          });

          if (
            event.type === 'meeting_start' &&
            selectedThreadId &&
            event.thread_id === selectedThreadId
          ) {
            setRelatedContext(prev => ({
              ...prev,
              ...getRelatedDecisionContextFromMeetingPayload(event.payload),
            }));
          }

          if (event.type === 'decision_required' || event.type === 'branch_proposed') {
            const card = eventToBlockerCard(event);
            if (card) {
              setDecisionCards(prev => {
                if (prev.find(item => item.id === card.id)) {
                  return prev.map(item => item.id === card.id ? card : item);
                }
                return [...prev, card];
              });
            }
          }

          if (event.type === 'run_state_changed' && event.payload.new_state === 'DONE') {
            setDecisionCards(prev => prev.filter(card =>
              card.status !== 'DONE' && card.status !== 'REJECTED'
            ));
          }
        },
        onError: (error) => {
          console.error('Event stream error:', error);
        },
      }
    );

    const handleCardAction = (event: any) => {
      handleDecisionCardAction(event.detail);
    };
    window.addEventListener('decision-card-action', handleCardAction);

    const handleBranchSelection = (event: any) => {
      const { alternatives, recommendedBranch } = event.detail;
      setBranchDialog({
        title: 'Select Execution Plan',
        alternatives,
        recommendedBranch,
        onSubmit: async (selectedPlaybookCode: string) => {
          setBranchDialog(null);
          try {
            const response = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/decision-cards/${event.detail.branchId}/confirm`,
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

            setDecisionCards(prev => prev.filter(card => card.id !== event.detail.branchId));
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
  }, [apiUrl, workspaceId, handleDecisionCardAction, selectedThreadId]);

  useEffect(() => {
    if (!selectedThreadId) {
      setRelatedContext(emptyRelatedDecisionContext);
      setRelatedMemoryLoading(false);
      return;
    }

    let cancelled = false;

    const loadRelatedMemory = async () => {
      try {
        setRelatedMemoryLoading(true);
        const params = new URLSearchParams();
        params.set('event_types', 'memory_writeback,meeting_start');
        params.set('thread_id', selectedThreadId);
        params.set('limit', '10');
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load related governed memory: ${response.status}`);
        }
        const data = await response.json();
        const latestMeetingStartEvent = (data.events || []).find(
          (event: any) => event?.type === 'meeting_start'
        );
        const latestMemoryEvent = (data.events || []).find(
          (event: any) => typeof event?.payload?.memory_item_id === 'string' && event.payload.memory_item_id
        );

        if (!cancelled) {
          setRelatedContext(getRelatedDecisionContextFromEvents(
            latestMeetingStartEvent,
            latestMemoryEvent
          ));
        }
      } catch (err) {
        console.error('Failed to load related governed memory for decision panel:', err);
        if (!cancelled) {
          setRelatedContext(emptyRelatedDecisionContext);
        }
      } finally {
        if (!cancelled) {
          setRelatedMemoryLoading(false);
        }
      }
    };

    void loadRelatedMemory();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, selectedThreadId, workspaceId]);

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
            .map((event: UnifiedEvent) => eventToBlockerCard(event))
            .filter((card: DecisionCardData | null): card is DecisionCardData => card !== null);
          setDecisionCards(cards);
        }
      } catch (err) {
        console.error('Failed to load initial events:', err);
      }
    };

    loadInitialEvents();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
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
  }, [loadIntentCards]);

  const pendingCards = useMemo(() => getPendingIntentCards(intentCards), [intentCards]);
  const historyCards = useMemo(() => getHistoryIntentCards(intentCards), [intentCards]);
  const sortedDecisionCards = useMemo(
    () => sortDecisionCards(decisionCards, currentUserId),
    [decisionCards, currentUserId]
  );
  const filteredDecisionCards = useMemo(
    () => filterDecisionCards(sortedDecisionCards, filter, currentUserId),
    [sortedDecisionCards, filter, currentUserId]
  );
  const blockerCount = useMemo(() => countBlockerCards(decisionCards), [decisionCards]);
  const assignedToMeCount = useMemo(
    () => countAssignedToMeCards(decisionCards, currentUserId),
    [decisionCards, currentUserId]
  );
  const openDecisionCount = useMemo(() => countOpenDecisionCards(decisionCards), [decisionCards]);
  const mentionedMeCount = useMemo(
    () => countMentionedMeCards(decisionCards, currentUserId),
    [decisionCards, currentUserId]
  );
  const waitingOnOthersCount = useMemo(
    () => countWaitingOnOthersCards(decisionCards, currentUserId),
    [decisionCards, currentUserId]
  );

  return (
    <DecisionPanelView
      workspaceId={workspaceId}
      apiUrl={apiUrl}
      workspace={workspace}
      onViewArtifact={onViewArtifact}
      onSwitchToOutcomes={onSwitchToOutcomes}
      loading={loading}
      pendingTaskCount={pendingTaskCount}
      onPendingTaskCountChange={setPendingTaskCount}
      currentUserId={currentUserId}
      filteredDecisionCards={filteredDecisionCards}
      pendingCards={pendingCards}
      historyCards={historyCards}
      blockerCount={blockerCount}
      assignedToMeCount={assignedToMeCount}
      openDecisionCount={openDecisionCount}
      mentionedMeCount={mentionedMeCount}
      waitingOnOthersCount={waitingOnOthersCount}
      filter={filter}
      onFilterChange={setFilter}
      showLegacyTasks={showLegacyTasks}
      onToggleLegacyTasks={() => setShowLegacyTasks(value => !value)}
      showHistory={showHistory}
      onToggleHistory={() => setShowHistory(value => !value)}
      relatedContext={relatedContext}
      relatedMemoryLoading={relatedMemoryLoading}
      inputDialog={inputDialog}
      branchDialog={branchDialog}
      onCloseInputDialog={() => setInputDialog(null)}
      onCloseBranchDialog={() => setBranchDialog(null)}
      onIntentStatusChange={loadIntentCards}
      onExpandCard={(cardId) => {
        console.log('Expand card:', cardId);
      }}
    />
  );
}
