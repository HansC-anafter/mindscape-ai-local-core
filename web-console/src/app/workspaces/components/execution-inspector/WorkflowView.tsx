'use client';

import React from 'react';
import WorkflowVisualization from '../WorkflowVisualization';
import type { WorkflowData } from './types/execution';

export interface WorkflowViewProps {
  workflowData: WorkflowData;
  executionId: string;
}

export default function WorkflowView({
  workflowData,
  executionId,
}: WorkflowViewProps) {
  if (!workflowData.workflow_result && !workflowData.handoff_plan) {
    return null;
  }

  return (
    <div className="col-span-2 h-full overflow-y-auto p-3">
      <WorkflowVisualization
        workflowResult={workflowData.workflow_result}
        handoffPlan={workflowData.handoff_plan}
        executionId={executionId}
      />
    </div>
  );
}
