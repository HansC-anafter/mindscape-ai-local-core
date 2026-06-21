'use client';

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { createExecutionStateEventHandler } from './executionState/eventHandlers';
import { initialExecutionState } from './executionState/initialState';
import { calculateProgress } from './executionState/progress';
import { loadExecutionStateSnapshot } from './executionState/resourceActions';
import type { ExecutionUIState, SSEEvent } from './executionState/types';

export type {
  ExecutionUIState,
  PipelineStage,
  ProducedArtifact,
  ThinkingStep,
  TimelineEntry,
  TreeStep,
} from './executionState/types';

export function useExecutionState(workspaceId: string, apiUrl: string = '') {
  const [state, setState] = useState<ExecutionUIState>(initialExecutionState);
  const throttleRef = useRef<NodeJS.Timeout | null>(null);
  const pendingThinkingSteps = useRef<string[]>([]);

  const addThinkingStep = useCallback((step: string) => {
    pendingThinkingSteps.current.push(step);

    if (throttleRef.current) return;

    throttleRef.current = setTimeout(() => {
      const steps = pendingThinkingSteps.current;
      pendingThinkingSteps.current = [];
      throttleRef.current = null;

      setState(prev => ({
        ...prev,
        thinkingContext: [
          ...prev.thinkingContext,
          ...steps.map((content, idx) => ({
            id: `thinking-${Date.now()}-${idx}`,
            content,
          })),
        ],
      }));
    }, 100);
  }, []);

  const handleEvent = useMemo(
    () => createExecutionStateEventHandler({
      setState,
      addThinkingStep,
      calculateProgress,
    }),
    [addThinkingStep],
  );

  const resetState = useCallback(() => {
    setState(initialExecutionState);
  }, []);

  const simulateExecution = useCallback((steps: Array<{ id: string; name: string; icon: string }>) => {
    handleEvent({ type: 'thinking_start' });

    setTimeout(() => {
      handleEvent({
        type: 'execution_plan',
        plan: {
          summary: `This execution: ${steps.length} steps`,
          steps: steps.map(s => ({ ...s, status: 'pending' })),
        },
      });
    }, 500);
  }, [handleEvent]);

  useEffect(() => {
    const handleExecutionEvent = (event: CustomEvent) => {
      if (event.detail && event.detail.type) {
        handleEvent(event.detail as SSEEvent);
      }
    };

    const handleClearPipeline = () => {
      setState(prev => prev.pipelineStage ? { ...prev, pipelineStage: null } : prev);
    };

    window.addEventListener('execution-event', handleExecutionEvent as EventListener);
    window.addEventListener('clear-pipeline-stage', handleClearPipeline as EventListener);
    return () => {
      window.removeEventListener('execution-event', handleExecutionEvent as EventListener);
      window.removeEventListener('clear-pipeline-stage', handleClearPipeline as EventListener);
    };
  }, [handleEvent]);

  useEffect(() => {
    if (!workspaceId || apiUrl == null) return;

    const loadState = async () => {
      const snapshot = await loadExecutionStateSnapshot(workspaceId, apiUrl);
      if (!snapshot) return;

      setState(prev => ({
        ...prev,
        trainSteps: snapshot.trainSteps,
        executionTree: snapshot.executionTree,
        thinkingTimeline: snapshot.thinkingTimeline,
        thinkingSummary: snapshot.thinkingSummary,
        overallProgress: snapshot.overallProgress,
        isExecuting: snapshot.isExecuting,
        aiTeamMembers: snapshot.aiTeamMembers,
      }));
    };

    void loadState();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    return () => {
      if (throttleRef.current) {
        clearTimeout(throttleRef.current);
      }
    };
  }, []);

  return {
    ...state,
    resetState,
    simulateExecution,
    handleEvent,
  };
}

export default useExecutionState;
