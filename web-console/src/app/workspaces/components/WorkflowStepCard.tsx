'use client';

import React from 'react';

interface ToolCall {
  id: string;
  execution_id: string;
  step_id: string;
  tool_name: string;
  tool_id?: string;
  parameters?: Record<string, any>;
  response?: Record<string, any>;
  status: string;
  error?: string;
  duration_ms?: number;
  factory_cluster?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

interface AgentCollaboration {
  id: string;
  execution_id: string;
  step_id: string;
  collaboration_type: string;
  participants: string[];
  topic: string;
  discussion?: Array<{ agent: string; content: string }>;
  status: string;
  result?: Record<string, any>;
  started_at?: string;
  completed_at?: string;
}

interface StageResult {
  id: string;
  execution_id: string;
  step_id: string;
  stage_name: string;
  result_type: string;
  content: Record<string, any>;
  preview?: string;
  requires_review: boolean;
  review_status?: string;
  artifact_id?: string;
  created_at: string;
}

interface ExecutionStep {
  id: string;
  execution_id: string;
  step_index: number;
  step_name: string;
  status: string;
  step_type: string;
  agent_type?: string;
  used_tools?: string[];
  assigned_agent?: string;
  collaborating_agents?: string[];
  description?: string;
  log_summary?: string;
  requires_confirmation: boolean;
  confirmation_prompt?: string;
  confirmation_status?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  failure_type?: string;
}

interface WorkflowStepCardProps {
  step: ExecutionStep;
  isActive: boolean;
  toolCalls?: ToolCall[];
  collaborations?: AgentCollaboration[];
  stageResults?: StageResult[];
  onConfirm?: (stepId: string) => void;
  onReject?: (stepId: string) => void;
}

export default function WorkflowStepCard({
  step,
  isActive,
  toolCalls = [],
  collaborations = [],
  stageResults = [],
  onConfirm,
  onReject
}: WorkflowStepCardProps) {
  const getStepStatusIcon = () => {
    if (step.status === 'completed') return '✓';
    if (step.status === 'running') return '⟳';
    if (step.status === 'waiting_confirmation') return '⏸';
    if (step.status === 'failed') return '✗';
    return '○';
  };

  const getStepStatusColor = () => {
    if (step.status === 'completed') return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700';
    if (step.status === 'running') return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700';
    if (step.status === 'waiting_confirmation') return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200 dark:border-yellow-700';
    if (step.status === 'failed') return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700';
    return 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700';
  };

  const getToolStatusIcon = (status: string) => {
    if (status === 'completed') return '✓';
    if (status === 'running') return '⟳';
    if (status === 'failed') return '✗';
    return '○';
  };

  const getToolStatusColor = (status: string) => {
    if (status === 'completed') return 'text-green-600 dark:text-green-400';
    if (status === 'running') return 'text-blue-600 dark:text-blue-400';
    if (status === 'failed') return 'text-red-600 dark:text-red-400';
    return 'text-gray-400 dark:text-gray-500';
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return '';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  return (
    <div className={`border dark:border-gray-700 rounded-lg p-4 transition-colors ${getStepStatusColor()} ${isActive ? 'ring-2 ring-blue-400 dark:ring-blue-600' : ''}`}>
      {/* Step Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start gap-3 flex-1">
          <div className={`text-lg font-semibold ${getStepStatusColor().split(' ')[0]}`}>
            {getStepStatusIcon()}
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">
              {step.step_name}
            </h4>
            <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
              {step.agent_type && (
                <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded border border-blue-200 dark:border-blue-700">
                  Agent: {step.agent_type}
                </span>
              )}
              {step.assigned_agent && (
                <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 rounded border border-gray-200 dark:border-gray-600">
                  {step.assigned_agent}
                </span>
              )}
              {step.used_tools && step.used_tools.length > 0 && (
                <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded border border-gray-200 dark:border-gray-600">
                  🔧 {step.used_tools.length} tool{step.used_tools.length > 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </div>
        <span className={`text-xs font-medium px-2 py-1 rounded ${getStepStatusColor()}`}>
          {step.status}
        </span>
      </div>

      {/* Step Description / Log Summary */}
      {step.log_summary && (
        <div className="mb-3 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded p-2 border border-gray-200 dark:border-gray-700">
          {step.log_summary}
        </div>
      )}

      {/* Agent Collaboration */}
      {collaborations.length > 0 && (
        <div className="mb-3 bg-white dark:bg-gray-800 rounded p-3 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-1">
              🤝 Agent 協作
            </span>
            <span className="text-xs text-gray-600 dark:text-gray-400">
              {collaborations[0].collaboration_type}
            </span>
          </div>
          <div className="text-xs text-gray-700 dark:text-gray-300 mb-2">
            <span className="font-medium">參與者:</span>{' '}
            {collaborations[0].participants.join(', ')}
          </div>
          {collaborations[0].topic && (
            <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
              <span className="font-medium">主題:</span> {collaborations[0].topic}
            </div>
          )}
          {collaborations[0].discussion && collaborations[0].discussion.length > 0 && (
            <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
              {collaborations[0].discussion.map((msg, i) => (
                <div key={i} className="text-xs bg-gray-50 dark:bg-gray-700 rounded p-2 border border-gray-100 dark:border-gray-600">
                  <span className="font-medium text-gray-900 dark:text-gray-100">{msg.agent}:</span>{' '}
                  <span className="text-gray-700 dark:text-gray-300">{msg.content}</span>
                </div>
              ))}
            </div>
          )}
          {collaborations[0].result && (
            <div className="mt-2 text-xs bg-green-50 dark:bg-green-900/20 rounded p-2 border border-green-200 dark:border-green-700">
              <span className="font-medium text-green-800 dark:text-green-300">協作結果:</span>{' '}
              <span className="text-green-700 dark:text-green-300">
                {JSON.stringify(collaborations[0].result).substring(0, 100)}
                {JSON.stringify(collaborations[0].result).length > 100 ? '...' : ''}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Tool Calls */}
      {toolCalls.length > 0 && (
        <div className="mb-3 bg-white dark:bg-gray-800 rounded p-3 border border-gray-200 dark:border-gray-700">
          <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2 flex items-center gap-1">
            🔧 工具調用 ({toolCalls.length})
          </h5>
          <div className="space-y-2">
            {toolCalls.map((toolCall) => (
              <div
                key={toolCall.id}
                className="text-xs bg-gray-50 dark:bg-gray-700 rounded p-2 border border-gray-100 dark:border-gray-600"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`font-medium ${getToolStatusColor(toolCall.status)}`}>
                      {getToolStatusIcon(toolCall.status)}
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{toolCall.tool_name}</span>
                    {toolCall.factory_cluster && (
                      <span className="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded text-[10px]">
                        {toolCall.factory_cluster}
                      </span>
                    )}
                  </div>
                  {toolCall.duration_ms && (
                    <span className="text-gray-500 dark:text-gray-400 text-[10px]">
                      {formatDuration(toolCall.duration_ms)}
                    </span>
                  )}
                </div>
                {toolCall.parameters && Object.keys(toolCall.parameters).length > 0 && (
                  <div className="text-[10px] text-gray-600 dark:text-gray-400 mt-1">
                    <span className="font-medium">參數:</span>{' '}
                    {JSON.stringify(toolCall.parameters).substring(0, 80)}
                    {JSON.stringify(toolCall.parameters).length > 80 ? '...' : ''}
                  </div>
                )}
                {toolCall.response && (
                  <div className="text-[10px] text-gray-700 dark:text-gray-300 mt-1 bg-white dark:bg-gray-800 rounded p-1 border border-gray-200 dark:border-gray-700">
                    <span className="font-medium">回應:</span>{' '}
                    {JSON.stringify(toolCall.response).substring(0, 100)}
                    {JSON.stringify(toolCall.response).length > 100 ? '...' : ''}
                  </div>
                )}
                {toolCall.error && (
                  <div className="text-[10px] text-red-700 dark:text-red-400 mt-1 bg-red-50 dark:bg-red-900/20 rounded p-1 border border-red-200 dark:border-red-700">
                    <span className="font-medium">錯誤:</span> {toolCall.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stage Results */}
      {stageResults.length > 0 && (
        <div className="mb-3 bg-white dark:bg-gray-800 rounded p-3 border border-gray-200 dark:border-gray-700">
          <h5 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            📦 階段性結果 ({stageResults.length})
          </h5>
          <div className="space-y-2">
            {stageResults.map((result) => (
              <div
                key={result.id}
                className="text-xs bg-gray-50 dark:bg-gray-700 rounded p-2 border border-gray-100 dark:border-gray-600"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-gray-900 dark:text-gray-100">{result.stage_name}</span>
                  <span className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-[10px]">
                    {result.result_type}
                  </span>
                </div>
                {result.preview && (
                  <div className="text-gray-700 dark:text-gray-300 mt-1">{result.preview}</div>
                )}
                {result.requires_review && (
                  <div className="mt-1 text-yellow-700 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 rounded px-1.5 py-0.5 border border-yellow-200 dark:border-yellow-700">
                    <span className="font-medium">需要審查</span>
                    {result.review_status && (
                      <span className="ml-1">({result.review_status})</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* User Confirmation */}
      {step.requires_confirmation && step.status === 'waiting_confirmation' && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded p-3">
          <div className="text-sm font-semibold text-yellow-800 dark:text-yellow-300 mb-2">
            ⏸ 等待確認
          </div>
          {step.confirmation_prompt && (
            <div className="text-sm text-yellow-700 dark:text-yellow-300 mb-3">
              {step.confirmation_prompt}
            </div>
          )}
          <div className="flex gap-2">
            {onConfirm && (
              <button
                onClick={() => onConfirm(step.id)}
                className="px-3 py-1.5 text-sm font-medium text-white bg-green-600 dark:bg-green-700 hover:bg-green-700 dark:hover:bg-green-600 rounded transition-colors"
              >
                確認並繼續
              </button>
            )}
            {onReject && (
              <button
                onClick={() => onReject(step.id)}
                className="px-3 py-1.5 text-sm font-medium text-white bg-red-600 dark:bg-red-700 hover:bg-red-700 dark:hover:bg-red-600 rounded transition-colors"
              >
                拒絕
              </button>
            )}
          </div>
        </div>
      )}

      {/* Error Information */}
      {step.error && (
        <div className="mt-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded p-3">
          <div className="text-sm font-semibold text-red-800 dark:text-red-300 mb-1">錯誤</div>
          <div className="text-sm text-red-700 dark:text-red-400">{step.error}</div>
          {step.failure_type && (
            <div className="text-xs text-red-600 dark:text-red-400 mt-1">
              類型: {step.failure_type}
            </div>
          )}
        </div>
      )}

      {/* Timing Information */}
      {(step.started_at || step.completed_at) && (
        <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700 pt-2">
          {step.started_at && (
            <div>開始: {new Date(step.started_at).toLocaleString()}</div>
          )}
          {step.completed_at && (
            <div>完成: {new Date(step.completed_at).toLocaleString()}</div>
          )}
        </div>
      )}
    </div>
  );
}


