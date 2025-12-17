'use client';

import React, { useState, useEffect } from 'react';
import { useT } from '@/lib/i18n';

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
  projectId?: string;  // 方案 1 & 2: 添加 project 归属信息
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
      // Don't reset loading state if we already have data (preserve content when switching tabs)
      if (playbookGroups.length === 0) {
        setLoading(true);
      }
      try {
        // If projectId is provided, load project-specific data
        // Only use projectId if it's not empty string
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
            // Check if response contains error (e.g., "Project not found")
            if (treeData.detail) {
              console.warn('[ExecutionSidebar] execution-tree API returned error:', treeData.detail);
              // If project not found, fallback to workspace-level API
              // Don't set playbookGroups to empty, keep existing state
            } else if (treeData.playbookGroups && Array.isArray(treeData.playbookGroups) && treeData.playbookGroups.length > 0) {
              // 收集所有执行，按全局时间排序，分配全局 runNumber
              const allExecutions: Array<{ exec: any; group: any }> = [];
              treeData.playbookGroups.forEach((group: any) => {
                if (group.executions && group.executions.length > 0) {
                  group.executions.forEach((exec: any) => {
                    allExecutions.push({ exec, group });
                  });
                }
              });

              // 按全局执行时间排序（最早的在前）
              allExecutions.sort((a, b) => {
                const timeA = new Date(a.exec.started_at || a.exec.created_at || 0).getTime();
                const timeB = new Date(b.exec.started_at || b.exec.created_at || 0).getTime();
                return timeA - timeB;
              });

              // 分配全局连续的 runNumber（1, 2, 3...）
              allExecutions.forEach((item, index) => {
                item.exec.runNumber = index + 1;
              });

              // 方案 1 & 2: 处理 playbookGroups，提取并保存每个 playbook 的 project 信息
              // Convert execution-tree API data to ExecutionSummary format
              const processedGroups = treeData.playbookGroups.map((group: any) => {
                // 从 executions 中提取 project_id 和 project_name
                let groupProjectId: string | undefined;
                let groupProjectName: string | undefined;

                // Convert executions to ExecutionSummary format
                const executionSummaries: ExecutionSummary[] = [];
                if (group.executions && group.executions.length > 0) {
                  // 从第一个 execution 中提取 project 信息（假设同一 playbook 的所有 execution 属于同一 project）
                  const firstExec = group.executions[0];
                  groupProjectId = firstExec.project_id || firstExec.execution_context?.project_id;
                  groupProjectName = firstExec.project_name || firstExec.execution_context?.project_name;

                  // Convert each execution to ExecutionSummary format
                  group.executions.forEach((exec: any) => {
                    const status = exec.status?.toLowerCase() || 'queued';
                    // Only create currentStep if we have valid step information
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

                  // 按执行时间排序（最早的在前），保持全局 runNumber
                  executionSummaries.sort((a, b) => {
                    return new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
                  });
                }

                // 如果 API 直接返回了 project 信息，使用它
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
            } else {
              // execution-tree returned empty array or no playbookGroups
              console.log('[ExecutionSidebar] execution-tree returned empty playbookGroups, keeping existing state');
            }
          } else if (executionTreeResponse && !executionTreeResponse.ok) {
            // execution-tree API returned error (e.g., 404 Project not found)
            console.warn('[ExecutionSidebar] execution-tree API failed:', executionTreeResponse.status, executionTreeResponse.statusText);
            // Fallback to workspace-level API if projectId was invalid
            // This will be handled by the else block below
          }
        } else {
          // Fallback: Load all workspace executions if no projectId
          try {
            const execResponse = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/executions?limit=50`
            );
            if (execResponse.ok) {
              const execData = await execResponse.json();
              const executions = execData.executions || [];

              // First, collect all executions and assign global runNumber
              const allExecutionsWithData = executions.map((exec: any) => ({
                exec,
                playbookCode: exec.playbook_code || 'unknown',
                startedAt: exec.started_at || exec.created_at || new Date().toISOString()
              }));

              // Sort all executions by global time (earliest first)
              allExecutionsWithData.sort((a, b) => {
                return new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
              });

              // Assign global continuous runNumber (1, 2, 3...)
              allExecutionsWithData.forEach((item, index) => {
                item.exec._globalRunNumber = index + 1;
              });

              // Group executions by playbook_code
              const groupMap = new Map<string, PlaybookGroup>();
              allExecutionsWithData.forEach(({ exec }) => {
                const playbookCode = exec.playbook_code || 'unknown';
                if (!groupMap.has(playbookCode)) {
                  // 方案 1 & 2: 从 execution 中提取 project 信息
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
                // Only create currentStep if we have valid step information
                const currentStepIndex = exec.current_step_index;
                const currentStepName = exec.current_step_name;
                const currentStep = (currentStepIndex !== null && currentStepIndex !== undefined) ? {
                  index: currentStepIndex + 1,
                  name: currentStepName || 'Step',
                  status: exec.status === 'paused' ? 'waiting_confirmation' as const : 'running' as const
                } : undefined;

                group.executions.push({
                  executionId: exec.execution_id,
                  runNumber: exec._globalRunNumber, // Use global runNumber
                  status: status as any,
                  startedAt: exec.started_at || exec.created_at || new Date().toISOString(),
                  currentStep,
                  totalSteps: exec.total_steps || 1,
                  playbookCode,
                  playbookName: exec.playbook_title || playbookCode
                });
                // Update stats
                if (status === 'running') group.stats.running++;
                else if (status === 'paused') group.stats.paused++;
                else if (status === 'queued') group.stats.queued++;
                else if (status === 'completed' || status === 'succeeded') group.stats.completed++;
                else if (status === 'failed') group.stats.failed++;
              });

              // For each playbook group, sort executions by time (to maintain order within group)
              groupMap.forEach((group) => {
                group.executions.sort((a, b) => {
                  return new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
                });
              });

              setPlaybookGroups(Array.from(groupMap.values()));
              setProjectName('All Executions');
            }
          } catch (err) {
            console.error('Failed to load workspace executions:', err);
          }
        }
      } catch (err) {
        console.error('Failed to load execution sidebar data:', err);
        // Keep existing state on error, don't clear playbookGroups
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [projectId, workspaceId, apiUrl]);

  // 方案 2: 如果提供了 projectId，先过滤只显示属于该 project 的 playbook
  const projectFilteredGroups = projectId
    ? playbookGroups.filter(group => {
        // 如果 playbook 有 projectId，只显示匹配的
        if (group.projectId) {
          return group.projectId === projectId;
        }
        // 如果没有 projectId 信息，假设属于当前 project（向后兼容）
        return true;
      })
    : playbookGroups;

  // 然后应用状态过滤
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
      // Define playbook execution order (earlier steps first, deployment last)
      const playbookOrder: { [key: string]: number } = {
        'obsidian_vault_organize': 1,
        'cis_mind_identity': 2,
        'cis_visual_identity': 2.5, // Can run concurrently with cis_mind_identity
        'site_spec_generation': 3,
        'style_system_gen': 4,
        'component_library_gen': 5,
        'multi_page_assembly': 6,
        'site_deploy_gcp_vm': 999, // Last step - deployment should be at the end
      };

      const orderA = playbookOrder[a.playbookCode] || 100;
      const orderB = playbookOrder[b.playbookCode] || 100;

      // Sort by playbook order (logical execution sequence)
      return orderA - orderB;
    });

  const globalStats = {
    totalRunning: playbookGroups.reduce((sum, g) => sum + g.stats.running, 0),
    totalPaused: playbookGroups.reduce((sum, g) => sum + g.stats.paused, 0),
    totalQueued: playbookGroups.reduce((sum, g) => sum + g.stats.queued, 0)
  };

  if (loading) {
    return (
      <div className="w-60 flex-shrink-0 border-r dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-4"></div>
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded mb-2"></div>
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Quick Filters */}
      <div className="p-3 border-b dark:border-gray-700">
        <div className="flex flex-wrap gap-1.5">
          {[
            { key: 'all', label: (t('all' as any) as string) || 'All', icon: '' },
            { key: 'waiting', label: (t('waiting' as any) as string) || 'Waiting', icon: '⏸️' },
            { key: 'running', label: t('running') || 'Running', icon: '🔄' },
            { key: 'failed', label: t('failed') || 'Failed', icon: '❌' }
          ].map(filter => (
            <button
              key={filter.key}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                filterStatus === filter.key
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-700'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}
              onClick={() => setFilterStatus(filter.key)}
            >
              {filter.icon && <span className="mr-1">{filter.icon}</span>}
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {/* Playbook Groups */}
      <div className="flex-1 overflow-y-auto">
        {filteredGroups.length === 0 ? (
          <div className="p-4 text-sm text-gray-500 dark:text-gray-400 text-center">
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

      {/* Global Stats */}
      {(globalStats.totalRunning > 0 || globalStats.totalPaused > 0 || globalStats.totalQueued > 0) && (
        <div className="p-3 border-t dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
            📊 {(t('concurrentStatus' as any) as string) || 'Concurrent Status'}
          </div>
          <div className="space-y-1">
            {globalStats.totalRunning > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-600 dark:text-gray-400">🔄 {t('running') || 'Running'}</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">{globalStats.totalRunning}</span>
              </div>
            )}
            {globalStats.totalPaused > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-600 dark:text-gray-400">⏸️ {(t('waitingConfirmation' as any) as string) || 'Waiting'}</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">{globalStats.totalPaused}</span>
              </div>
            )}
            {globalStats.totalQueued > 0 && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-600 dark:text-gray-400">⏳ {(t('queued' as any) as string) || 'Queued'}</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">{globalStats.totalQueued}</span>
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
        className="p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-xs">{expanded ? '▼' : '▶'}</span>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {group.playbookName}
            </span>
            {hasConcurrent && (
              <span className="text-xs text-blue-600 dark:text-blue-400" title={`${concurrentRunning} concurrent`}>
                🔄 ×{concurrentRunning}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {group.stats.paused > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300">
                ⏸️ {group.stats.paused}
              </span>
            )}
            {group.stats.queued > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                ⏳ {group.stats.queued}
              </span>
            )}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="bg-gray-50 dark:bg-gray-800/50">
          {group.executions
            .sort((a, b) => {
              // For executions of the same playbook, sort by start time (earliest first)
              // This shows the execution sequence in chronological order
              return new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
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
    queued: '⏳',
    running: '🔄',
    paused: '⏸️',
    completed: '✅',
    failed: '❌'
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) {
      return 'N/A';
    }
    try {
      const date = new Date(timeStr);
      if (isNaN(date.getTime())) {
        return 'N/A';
      }
      return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch {
      return 'N/A';
    }
  };

  return (
    <div
      className={`p-2 cursor-pointer border-l-2 transition-colors ${
        isSelected
          ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-400'
          : 'border-transparent hover:bg-gray-100 dark:hover:bg-gray-700'
      }`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
          [#{execution.runNumber}]
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">{formatTime(execution.startedAt)}</span>
        <span className="text-xs">{statusIcons[execution.status]}</span>
      </div>
      <div className="text-xs text-gray-600 dark:text-gray-400">
        {execution.status === 'completed' ? (
          <span>└─ {execution.totalSteps}/{execution.totalSteps} steps completed</span>
        ) : execution.status === 'failed' ? (
          <span>└─ Step {execution.currentStep?.index || 0}: Failed</span>
        ) : execution.currentStep ? (
          <span>
            └─ Step {execution.currentStep.index}/{execution.totalSteps}: {execution.currentStep.name}
          </span>
        ) : (
          <span>└─ Step ?/{execution.totalSteps}: Loading...</span>
        )}
      </div>
      {execution.currentStep?.status === 'waiting_confirmation' && (
        <div className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
          ⚠️ Needs confirmation
        </div>
      )}
      {['running', 'paused'].includes(execution.status) && (
        <div className="mt-1 h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 dark:bg-blue-400 transition-all"
            style={{
              width: `${(execution.currentStep.index / execution.totalSteps) * 100}%`
            }}
          />
        </div>
      )}
    </div>
  );
}
