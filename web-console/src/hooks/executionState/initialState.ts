import type { ExecutionUIState } from './types';

export const initialExecutionState: ExecutionUIState = {
  trainSteps: [],
  overallProgress: 0,
  isExecuting: false,
  thinkingContext: [],
  pipelineStage: null,
  currentRunId: null,
  aiTeamMembers: [],
  producedArtifacts: [],
  executionTree: [],
  thinkingTimeline: [],
};
