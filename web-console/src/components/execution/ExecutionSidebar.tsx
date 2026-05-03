'use client';

import React, { useState, useEffect } from 'react';
import { useT } from '@/lib/i18n';
import { getPlaybookMetadata } from '@/lib/i18n/locales/playbooks';
import { toTimestampMs, parseServerTimestamp } from '@/lib/time';

interface ExecutionSummary {
  executionId: string;
  runNumber: number;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed';
  startedAt: string;
  currentStep?: {
    index: number;
    name: string;
    status: 'running' | 'waiting_confirmation';
  };
  totalSteps: number;
  playbookCode: string;
  playbookName: string;
}

interface PlaybookGroup {
  playbookCode: string;
  playbookName: string;
  executions: ExecutionSummary[];
  stats: {
    running: number;
    paused: number;
    queued: number;
    completed: number;
    failed: number;
  };
  projectId?: string;
  projectName?: string;
}

interface ExecutionSidebarProps {
  projectId: string;
  workspaceId: string;
  apiUrl: string;
  storyThreadId?: string;
  currentExecutionId: string;
  onSelectExecution: (executionId: string) => void;
}

export default function ExecutionSidebar({
  projectId,
  workspaceId,
  apiUrl,
  storyThreadId,
  currentExecutionId,
  onSelectExecution
}: ExecutionSidebarProps) {
  const t = useT();
  const [playbookGroups, setPlaybookGroups] = useState<PlaybookGroup[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [projectName, setProjectName] = useState<string>('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        if (projectId && projectId.trim() !== '') {
          const [projectResponse, executionTreeResponse] = await Promise.all([
            fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}`).catch(() => null),
            fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects/${projectId}/execution-tree`).catch(() => null)
          ]);

          if (projectResponse?.ok) {
            const projectData = await projectResponse.json();
            setProjectName(projectData.name || projectData.title || 'Project');
          }

          if (executionTreeResponse?.ok) {
            const treeData = await executionTreeResponse.json();
            if (treeData.detail) {
              return;
            } else if (treeData.playbookGroups && Array.isArray(treeData.playbookGroups) && treeData.playbookGroups.length > 0) {
              const allExecutions: Array<{ exec: any; group: any }> = [];
              treeData.playbookGroups.forEach((group: any) => {
                if (group.executions && group.executions.length > 0) {
                  group.executions.forEach((exec: any) => {
                    allExecutions.push({ exec, group });
                  });
                }
              });

              allExecutions.sort((a, b) => {
                const timeA = toTimestampMs(a.exec.started_at || a.exec.created_at) ?? 0;
                const timeB = toTimestampMs(b.exec.started_at || b.exec.created_at) ?? 0;
                return timeA - timeB;
              });

              allExecutions.forEach((item, index) => {
                item.exec.runNumber = index + 1;
              });

              const processedGroups = treeData.playbookGroups.map((group: any) => {
                let groupProjectId: string | undefined;
                let groupProjectName: string | undefined;

                const executionSummaries: ExecutionSummary[] = [];
                if (group.executions && group.executions.length > 0) {
                  const firstExec = group.executions[0];
                  groupProjectId = firstExec.project_id || firstExec.execution_context?.project_id;
                  groupProjectName = firstExec.project_name || firstExec.execution_context?.project_name;

                  group.executions.forEach((exec: any) => {
                    const status = exec.status?.toLowerCase() || 'queued';
                    const currentStepIndex = exec.current_step_index;
                    const currentStepName = exec.current_step_name;
                    const currentStep = (currentStepIndex !== null && currentStepIndex !== undefined) ? {
                      index: currentStepIndex + 1,
                      name: currentStepName || 'Step',
                      status: exec.status === 'paused' ? 'waiting_confirmation' as const : 'running' as const
                    } : undefined;

                    executionSummaries.push({
                      executionId: exec.execution_id,
                      runNumber: exec.runNumber || exec.run_number || 0,
                      status: status as any,
                      startedAt: exec.started_at || exec.created_at || new Date().toISOString(),
                      currentStep,
                      totalSteps: exec.total_steps || 1,
                      playbookCode: exec.playbook_code || group.playbookCode || 'unknown',
                      playbookName: exec.playbook_title || group.playbookName || exec.playbook_code || 'unknown'
                    });
                  });

                  executionSummaries.sort((a, b) => {
                    return (toTimestampMs(a.startedAt) ?? 0) - (toTimestampMs(b.startedAt) ?? 0);
                  });
                }

                if (group.project_id) {
                  groupProjectId = group.project_id;
                }
                if (group.project_name) {
                  groupProjectName = group.project_name;
                }

                return {
                  playbookCode: group.playbookCode || 'unknown',
                  playbookName: group.playbookName || group.playbookCode || 'unknown',
                  executions: executionSummaries,
                  stats: group.stats || { running: 0, paused: 0, queued: 0, completed: 0, failed: 0 },
                  projectId: groupProjectId,
                  projectName: groupProjectName
                };
              });

              setPlaybookGroups(processedGroups);
            }
          } else if (executionTreeResponse && !executionTreeResponse.ok) {
          }
        } else {
          try {
            const execResponse = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=50&task_type=execution&include_completed=true`
            );
            if (execResponse.ok) {
              const execData = await execResponse.json();
              const executions = execData.tasks || [];

              const allExecutionsWithData = executions.map((exec: any) => ({
                exec,
                playbookCode: exec.playbook_code || exec.pack_id || 'unknown',
                startedAt: exec.started_at || exec.created_at || new Date().toISOString()
              }));

              allExecutionsWithData.sort((a: { exec: any; playbookCode: string; startedAt: string }, b: { exec: any; playbookCode: string; startedAt: string }) => {
                return (toTimestampMs(a.startedAt) ?? 0) - (toTimestampMs(b.startedAt) ?? 0);
              });

              allExecutionsWithData.forEach((item: { exec: any; playbookCode: string; startedAt: string }, index: number) => {
                item.exec._globalRunNumber = index + 1;
              });

              const groupMap = new Map<string, PlaybookGroup>();
              allExecutionsWithData.forEach(({ exec }: { exec: any }) => {
                const playbookCode = exec.playbook_code || exec.pack_id || 'unknown';
                if (!groupMap.has(playbookCode)) {
                  const execProjectId = exec.project_id || exec.execution_context?.project_id;
                  const execProjectName = exec.project_name || exec.execution_context?.project_name;

                  groupMap.set(playbookCode, {
                    playbookCode,
                    playbookName: exec.playbook_title || playbookCode,
                    executions: [],
                    stats: { running: 0, paused: 0, queued: 0, completed: 0, failed: 0 },
                    projectId: execProjectId,
                    projectName: execProjectName
                  });
                }
                const group = groupMap.get(playbookCode)!;
                const status = exec.status?.toLowerCase() || 'queued';
                const currentStepIndex = exec.current_step_index;
                const currentStepName = exec.current_step_name;
                const currentStep = (currentStepIndex !== null && currentStepIndex !== undefined) ? {
                  index: currentStepIndex + 1,
                  name: currentStepName || 'Step',
                  status: exec.status === 'paused' ? 'waiting_confirmation' as const : 'running' as const
                } : undefined;

                group.executions.push({
                  executionId: exec.execution_id,
                  runNumber: exec._globalRunNumber,
                  status: status as any,
                  startedAt: exec.started_at || exec.created_at || new Date().toISOString(),
                  currentStep,
                  totalSteps: exec.total_steps || 1,
                  playbookCode,
                  playbookName: exec.playbook_title || playbookCode
                });
                if (status === 'running') group.stats.running++;
                else if (status === 'paused') group.stats.paused++;
                else if (status === 'queued') group.stats.queued++;
                else if (status === 'completed' || status === 'succeeded') group.stats.completed++;
                else if (status === 'failed') group.stats.failed++;
              });

              groupMap.forEach((group) => {
                group.executions.sort((a, b) => {
                  return (toTimestampMs(a.startedAt) ?? 0) - (toTimestampMs(b.startedAt) ?? 0);
                });
              });

              setPlaybookGroups(Array.from(groupMap.values()));
              setProjectName('All Executions');
            }
          } catch {
          }
        }
      } catch {
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId, workspaceId, apiUrl]);

  const projectFilteredGroups = projectId
    ? playbookGroups.filter(group => {
      if (group.projectId) {
        return group.projectId === projectId;
      }
      return true;
    })
    : playbookGroups;

  const filteredGroups = projectFilteredGroups.map(group => ({
    ...group,
    executions: filterStatus === 'all'
      ? group.executions
      : group.executions.filter(e => {
        if (filterStatus === 'waiting') {
          return e.status === 'paused' || e.currentStep?.status === 'waiting_confirmation';
        }
        if (filterStatus === 'running') {
          return e.status === 'running';
        }
        if (filterStatus === 'failed') {
          return e.status === 'failed';
        }
        return true;
      })
  })).filter(group => group.executions.length > 0)
    .sort((a, b) => {
      const playbookOrder: { [key: string]: number } = {
        'obsidian_vault_organize': 1,
        'cis_mind_identity': 2,
        'cis_visual_identity': 2.5,
        'site_spec_generation': 3,
        'style_system_gen': 4,
        'component_library_gen': 5,
        'multi_page_assembly': 6,
        'site_deploy_gcp_vm': 999,
      };

      const orderA = playbookOrder[a.playbookCode] || 100;
      const orderB = playbookOrder[b.playbookCode] || 100;

      return orderA - orderB;
    });

  const globalStats = {
    totalRunning: playbookGroups.reduce((sum, g) => sum + g.stats.running, 0),
    totalPaused: playbookGroups.reduce((sum, g) => sum + g.stats.paused, 0),
    totalQueued: playbookGroups.reduce((sum, g) => sum + g.stats.queued, 0)
  };

  if (loading) {
    return (
      <div className="w-60 flex-shrink-0 border-r dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-default dark:bg-gray-700 rounded w-3/4 mb-4"></div>
          <div className="h-8 bg-default dark:bg-gray-700 rounded mb-2"></div>
          <div className="h-8 bg-default dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col bg-surface-secondary dark:bg-gray-900">
      <div className="p-3 border-b dark:border-gray-700">
        <div className="flex flex-wrap gap-1.5">
          {[
            { key: 'all', label: (t('all' as any) as string) || 'All', icon: '' },
            { key: 'waiting', label: (t('waiting' as any) as string) || 'Waiting', icon: 'WAIT' },
            { key: 'running', label: t('running' as any) || 'Running', icon: 'RUN' },
            { key: 'failed', label: t('failed' as any) || 'Failed', icon: 'ERR' }
          ].map(filter => (
            <button
              key={filter.key}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${filterStatus === filter.key
                ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300 border border-accent dark:border-blue-700'
                : 'bg-surface-secondary dark:bg-gray-800 text-primary dark:text-gray-300 border border-default dark:border-gray-600 hover:bg-surface-accent dark:hover:bg-gray-700'
                }`}
              onClick={() => setFilterStatus(filter.key)}
            >
              {filter.icon && <span className="mr-1">{filter.icon}</span>}
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filteredGroups.length === 0 ? (
          <div className="p-4 text-sm text-secondary dark:text-gray-400 text-center">
            {(t('noExecutions' as any) as string) || 'No executions found'}
          </div>
        ) : (
          filteredGroups.map(group => (
            <PlaybookExecutionGroup
              key={group.playbookCode}
              group={group}
              currentExecutionId={currentExecutionId}
              onSelectExecution={onSelectExecution}
            />
          ))
        )}
      </div>

      {(globalStats.totalRunning > 0 || globalStats.totalPaused > 0 || globalStats.totalQueued > 0) && (
        <div className="p-3 border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-800">
          <div className="text-xs font-semibold text-primary dark:text-gray-300 mb-2">
            {(t('concurrentStatus' as any) as string) || 'Concurrent Status'}
          </div>
          <div className="space-y-1">
            {globalStats.totalRunning > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-secondary dark:text-gray-400">RUN {t('running' as any) || 'Running'}</span>
                <span className="font-medium text-primary dark:text-gray-100">{globalStats.totalRunning}</span>
              </div>
            )}
            {globalStats.totalPaused > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-secondary dark:text-gray-400">WAIT {(t('waitingConfirmation' as any) as string) || 'Waiting'}</span>
                <span className="font-medium text-primary dark:text-gray-100">{globalStats.totalPaused}</span>
              </div>
            )}
            {globalStats.totalQueued > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-secondary dark:text-gray-400">QUE {(t('queued' as any) as string) || 'Queued'}</span>
                <span className="font-medium text-primary dark:text-gray-100">{globalStats.totalQueued}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface PlaybookExecutionGroupProps {
  group: PlaybookGroup;
  currentExecutionId: string;
  onSelectExecution: (executionId: string) => void;
}

function PlaybookExecutionGroup({
  group,
  currentExecutionId,
  onSelectExecution
}: PlaybookExecutionGroupProps) {
  const [expanded, setExpanded] = useState(true);
  const concurrentRunning = group.executions.filter(e => e.status === 'running').length;
  const hasConcurrent = concurrentRunning > 1;

  return (
    <div className="border-b dark:border-gray-700">
      <div
        className="p-3 cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-xs">{expanded ? '-' : '+'}</span>
            <span className="text-sm font-medium text-primary dark:text-gray-100 truncate">
              {group.playbookName}
            </span>
            {hasConcurrent && (
              <span className="text-xs text-accent dark:text-blue-400" title={`${concurrentRunning} concurrent`}>
                RUN x{concurrentRunning}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {group.stats.paused > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300">
                WAIT {group.stats.paused}
              </span>
            )}
            {group.stats.queued > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300">
                QUE {group.stats.queued}
              </span>
            )}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="bg-surface-secondary dark:bg-gray-800/50">
          {group.executions
            .sort((a, b) => {
              return (toTimestampMs(a.startedAt) ?? 0) - (toTimestampMs(b.startedAt) ?? 0);
            })
            .map((execution, index) => (
              <ExecutionItem
                key={`${execution.executionId}-${execution.runNumber}-${index}`}
                execution={execution}
                isSelected={execution.executionId === currentExecutionId}
                onClick={() => onSelectExecution(execution.executionId)}
              />
            ))}
        </div>
      )}
    </div>
  );
}

interface ExecutionItemProps {
  execution: ExecutionSummary;
  isSelected: boolean;
  onClick: () => void;
}

function ExecutionItem({ execution, isSelected, onClick }: ExecutionItemProps) {
  const statusIcons = {
    queued: 'QUE',
    running: 'RUN',
    paused: 'WAIT',
    completed: 'DONE',
    failed: 'ERR'
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) {
      return 'N/A';
    }
    const date = parseServerTimestamp(timeStr);
    if (!date) {
      return 'N/A';
    }
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div
      className={`p-2 cursor-pointer border-l-2 transition-colors ${isSelected
        ? 'bg-accent-10 dark:bg-blue-900/20 border-accent dark:border-blue-400'
        : 'border-transparent hover:bg-surface-accent dark:hover:bg-gray-700'
        }`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-primary dark:text-gray-100">
          {(() => {
            if (execution.playbookName && execution.playbookName !== 'unknown') {
              return execution.playbookName;
            }

            if (execution.playbookCode) {
              const playbookName = getPlaybookMetadata(execution.playbookCode, 'name', 'en');
              if (playbookName) {
                return playbookName;
              }
              return execution.playbookCode;
            }

            return `[#${execution.runNumber}]`;
          })()}
        </span>
        <span className="text-xs text-secondary dark:text-gray-400">{formatTime(execution.startedAt)}</span>
        <span className="text-xs">{statusIcons[execution.status]}</span>
      </div>
      <div className="text-xs text-secondary dark:text-gray-400">
        {execution.status === 'completed' ? (
          <span>- {execution.totalSteps}/{execution.totalSteps} steps completed</span>
        ) : execution.status === 'failed' ? (
          <span>- Step {execution.currentStep?.index || 0}: Failed</span>
        ) : execution.currentStep ? (
          <span>
            - Step {execution.currentStep.index}/{execution.totalSteps}: {execution.currentStep.name}
          </span>
        ) : (
          <span>- Step ?/{execution.totalSteps}: Loading...</span>
        )}
      </div>
      {execution.currentStep?.status === 'waiting_confirmation' && (
        <div className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
          Warning: Needs confirmation
        </div>
      )}
      {['running', 'paused'].includes(execution.status) && (
        <div className="mt-1 h-1 bg-default dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent dark:bg-blue-400 transition-all"
            style={{
              width: `${((execution.currentStep?.index || 0) / execution.totalSteps) * 100}%`
            }}
          />
        </div>
      )}
    </div>
  );
}
