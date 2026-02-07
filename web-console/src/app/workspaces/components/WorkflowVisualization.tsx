'use client';

import React, { useMemo } from 'react';
import WorkflowStepCard from './WorkflowStepCard';

interface WorkflowStep {
  playbook_code: string;
  kind?: 'user_workflow' | 'system_tool';
  status?: 'pending' | 'running' | 'completed' | 'error' | 'skipped';
  interaction_mode?: string[];
  inputs?: Record<string, any>;
  outputs?: Record<string, any>;
  error?: string;
  error_type?: string;
  attempts?: number;
  retries_exhausted?: boolean;
  started_at?: string;
  completed_at?: string;
  condition?: string;
}

interface WorkflowVisualizationProps {
  workflowResult: {
    steps: Record<string, WorkflowStep>;
    context?: Record<string, any>;
  };
  handoffPlan?: {
    steps: Array<{
      playbook_code: string;
      kind: string;
      interaction_mode: string[];
      condition?: string;
      inputs?: Record<string, any>;
    }>;
  };
  executionId?: string;
}

export default function WorkflowVisualization({
  workflowResult,
  handoffPlan,
  executionId
}: WorkflowVisualizationProps) {
  const dependencyGraph = useMemo(() => {
    if (!handoffPlan) return {};

    const graph: Record<string, string[]> = {};
    const stepMap = new Map(handoffPlan.steps.map(s => [s.playbook_code, s]));

    handoffPlan.steps.forEach(step => {
      const dependencies: string[] = [];

      if (step.inputs) {
        Object.values(step.inputs).forEach(value => {
          if (typeof value === 'string' && value.startsWith('$previous.')) {
            const parts = value.split('.');
            if (parts.length >= 2) {
              const prevCode = parts[1];
              if (stepMap.has(prevCode)) {
                dependencies.push(prevCode);
              }
            }
          }
        });
      }

      graph[step.playbook_code] = dependencies;
    });

    return graph;
  }, [handoffPlan]);

  const stepOrder = useMemo(() => {
    if (!handoffPlan) return [];

    const visited = new Set<string>();
    const order: string[] = [];
    const graph = dependencyGraph;

    const visit = (code: string) => {
      if (visited.has(code)) return;
      visited.add(code);

      const deps = graph[code] || [];
      deps.forEach(dep => visit(dep));

      order.push(code);
    };

    handoffPlan.steps.forEach(step => visit(step.playbook_code));
    return order;
  }, [handoffPlan, dependencyGraph]);

  const getStepStatus = (playbookCode: string): WorkflowStep['status'] => {
    const step = workflowResult.steps[playbookCode];
    if (!step) return 'pending';
    return (step.status as WorkflowStep['status']) || 'pending';
  };

  const getStepKindLabel = (kind: string) => {
    if (kind === 'system_tool') return 'System Tool';
    if (kind === 'user_workflow') return 'User Workflow';
    return kind;
  };

  const getStepKindColor = (kind: string) => {
    if (kind === 'system_tool') return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700';
    if (kind === 'user_workflow') return 'bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 border-gray-400 dark:border-gray-600';
    return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700';
      case 'running':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700';
      case 'error':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700';
      case 'skipped':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✓';
      case 'running':
        return '⟳';
      case 'error':
        return '✗';
      case 'skipped':
        return '⊘';
      default:
        return '○';
    }
  };

  if (!handoffPlan || handoffPlan.steps.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500 dark:text-gray-400">
        No workflow steps to display
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Workflow Execution
        </h3>
        {executionId && (
          <span className="text-xs text-gray-500 dark:text-gray-400">ID: {executionId}</span>
        )}
      </div>

      <div className="space-y-6">
        {stepOrder.map((playbookCode, index) => {
          const step = workflowResult.steps[playbookCode];
          const planStep = handoffPlan.steps.find(s => s.playbook_code === playbookCode);
          const status = getStepStatus(playbookCode);
          const dependencies = dependencyGraph[playbookCode] || [];
          const isParallel = index > 0 && dependencies.length === 0;

          return (
            <div key={playbookCode} className="relative">
              {index > 0 && (
                <div className="absolute left-6 top-0 w-0.5 h-6 bg-gray-300 dark:bg-gray-600 -translate-y-full" />
              )}

              <div className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center text-lg font-semibold border-2 ${getStatusColor(status || 'pending')}`}
                  >
                    {getStatusIcon(status || 'pending')}
                  </div>
                  {index < stepOrder.length - 1 && (
                    <div className="w-0.5 h-12 bg-gray-300 dark:bg-gray-600 mt-2" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className={`border rounded-lg p-4 ${getStatusColor(status || 'pending')}`}>
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">
                          {playbookCode}
                        </h4>
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          {planStep && (
                            <span className={`px-2 py-0.5 rounded border ${getStepKindColor(planStep.kind)}`}>
                              {getStepKindLabel(planStep.kind)}
                            </span>
                          )}
                          {isParallel && (
                            <span className="px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded border border-indigo-300 dark:border-indigo-700">
                              Parallel
                            </span>
                          )}
                          {planStep?.condition && (
                            <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded border border-orange-300 dark:border-orange-700">
                              Conditional
                            </span>
                          )}
                          {planStep?.interaction_mode?.includes('silent') && (
                            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded border border-gray-300 dark:border-gray-600">
                              Silent
                            </span>
                          )}
                        </div>
                      </div>
                      <span className={`text-xs font-medium px-2 py-1 rounded ${getStatusColor(status || 'pending')}`}>
                        {status}
                      </span>
                    </div>

                    {dependencies.length > 0 && (
                      <div className="mb-2 text-xs text-gray-600 dark:text-gray-400">
                        <span className="font-medium">Depends on:</span>{' '}
                        {dependencies.map((dep, i) => (
                          <span key={dep}>
                            {i > 0 && ', '}
                            <span className="text-blue-600 dark:text-blue-400">{dep}</span>
                          </span>
                        ))}
                      </div>
                    )}

                    {step && (
                      <div className="mt-3 space-y-2">
                        {step.outputs && Object.keys(step.outputs).length > 0 && (
                          <div className="text-xs bg-white dark:bg-gray-800 rounded p-2 border border-gray-200 dark:border-gray-700">
                            <span className="font-medium text-gray-700 dark:text-gray-300">Outputs:</span>{' '}
                            <span className="text-gray-600 dark:text-gray-400">
                              {Object.keys(step.outputs).join(', ')}
                            </span>
                          </div>
                        )}

                        {step.error && (
                          <div className="text-xs bg-red-50 dark:bg-red-900/20 rounded p-2 border border-red-200 dark:border-red-700">
                            <span className="font-medium text-red-800 dark:text-red-300">Error:</span>{' '}
                            <span className="text-red-700 dark:text-red-400">{step.error}</span>
                            {step.error_type && (
                              <span className="ml-2 text-red-600 dark:text-red-400">({step.error_type})</span>
                            )}
                          </div>
                        )}

                        {step.attempts && step.attempts > 1 && (
                          <div className="text-xs text-gray-600 dark:text-gray-400">
                            Retried {step.attempts - 1} time(s)
                          </div>
                        )}

                        {step.started_at && (
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            Started: {new Date(step.started_at).toLocaleString()}
                          </div>
                        )}

                        {step.completed_at && (
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            Completed: {new Date(step.completed_at).toLocaleString()}
                          </div>
                        )}
                      </div>
                    )}

                    {planStep?.condition && (
                      <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded p-2 border border-gray-200 dark:border-gray-700">
                        <span className="font-medium">Condition:</span>{' '}
                        <code className="text-gray-700 dark:text-gray-300">{planStep.condition}</code>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {workflowResult.context && Object.keys(workflowResult.context).length > 0 && (
        <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">Workflow Context</h4>
          <pre className="text-xs text-gray-700 dark:text-gray-300 overflow-x-auto">
            {JSON.stringify(workflowResult.context, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

