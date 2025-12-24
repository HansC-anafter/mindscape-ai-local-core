'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { subscribeEventStream, eventToProgress, UnifiedEvent, ExecutionStatus } from './eventProjector';
import { AlertCircle, CheckCircle, Clock, Play, Loader } from 'lucide-react';
import { CostWarningBanner } from './governance/CostWarningBanner';
import { GovernanceStatusIndicator } from './governance/GovernanceStatusIndicator';

interface ExecutionStatusPanelProps {
  workspaceId: string;
  apiUrl: string;
  onViewArtifact?: (artifact: any) => void;
}

export function ExecutionStatusPanel({
  workspaceId,
  apiUrl,
  onViewArtifact,
}: ExecutionStatusPanelProps) {
  const [events, setEvents] = useState<UnifiedEvent[]>([]);
  const [status, setStatus] = useState<ExecutionStatus>({
    status: 'UNKNOWN',
    message: 'Status unknown',
  });
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [costData, setCostData] = useState<{
    currentUsage: number;
    quota: number;
    estimatedCost?: number;
  } | null>(null);
  const [governanceStatus, setGovernanceStatus] = useState<
    Array<{
      layer: 'cost' | 'node' | 'policy' | 'preflight';
      status: 'passed' | 'failed' | 'warning' | 'pending';
      message?: string;
    }>
  >([]);

  useEffect(() => {
    const unsubscribe = subscribeEventStream(
      workspaceId,
      {
        apiUrl,
        eventTypes: ['run_state_changed', 'artifact_created', 'decision_required'],
        onEvent: (event: UnifiedEvent) => {
          setEvents(prev => {
            if (prev.find(e => e.id === event.id)) {
              return prev;
            }
            return [...prev, event];
          });
        },
        onError: (error) => {
          console.error('Event stream error:', error);
        },
      }
    );

    return () => {
      unsubscribe();
    };
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const loadInitialEvents = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?event_types=run_state_changed,artifact_created,decision_required&limit=100`
        );
        if (response.ok) {
          const data = await response.json();
          const initialEvents = data.events || [];
          setEvents(initialEvents);
        }
      } catch (err) {
        console.error('Failed to load initial events:', err);
      }
    };

    loadInitialEvents();
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const loadCostData = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/cost/monitoring?period=day`
        );
        if (response.ok) {
          const data = await response.json();
          setCostData({
            currentUsage: data.current_usage || 0,
            quota: data.quota || 10,
            estimatedCost: data.estimated_cost,
          });
        }
      } catch (err) {
        // Cost monitoring is Cloud-only, ignore errors in Local-Core
        console.debug('Cost monitoring not available:', err);
      }
    };

    loadCostData();
    const interval = setInterval(loadCostData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [workspaceId, apiUrl]);

  useEffect(() => {
    const { status: newStatus, artifacts: newArtifacts } = eventToProgress(events);
    setStatus(newStatus);
    setArtifacts(newArtifacts);

    // Extract governance status from events
    const governanceEvents = events.filter(
      (e) => e.type === 'decision_required' && e.payload?.governance_decision
    );
    const statusMap = new Map<
      'cost' | 'node' | 'policy' | 'preflight',
      'passed' | 'failed' | 'warning' | 'pending'
    >();

    governanceEvents.forEach((event) => {
      const govDecision = event.payload?.governance_decision;
      if (govDecision) {
        const currentStatus = statusMap.get(govDecision.layer);
        if (!currentStatus || currentStatus === 'pending') {
          statusMap.set(
            govDecision.layer,
            govDecision.approved ? 'passed' : 'failed'
          );
        }
      }
    });

    const statusArray = Array.from(statusMap.entries()).map(([layer, status]) => ({
      layer,
      status,
    }));

    // Add pending status for layers not found in events
    const allLayers: Array<'cost' | 'node' | 'policy' | 'preflight'> = [
      'cost',
      'node',
      'policy',
      'preflight',
    ];
    allLayers.forEach((layer) => {
      if (!statusMap.has(layer)) {
        statusArray.push({ layer, status: 'pending' as const });
      }
    });

    setGovernanceStatus(statusArray);
  }, [events]);

  const statusConfig = useMemo(() => {
    switch (status.status) {
      case 'WAITING_HUMAN':
        return {
          icon: AlertCircle,
          color: 'text-yellow-600 dark:text-yellow-400',
          bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
          borderColor: 'border-yellow-200 dark:border-yellow-800',
        };
      case 'READY':
        return {
          icon: Play,
          color: 'text-blue-600 dark:text-blue-400',
          bgColor: 'bg-blue-50 dark:bg-blue-900/20',
          borderColor: 'border-blue-200 dark:border-blue-800',
        };
      case 'RUNNING':
        return {
          icon: Loader,
          color: 'text-green-600 dark:text-green-400',
          bgColor: 'bg-green-50 dark:bg-green-900/20',
          borderColor: 'border-green-200 dark:border-green-800',
        };
      case 'DONE':
        return {
          icon: CheckCircle,
          color: 'text-gray-600 dark:text-gray-400',
          bgColor: 'bg-gray-50 dark:bg-gray-800',
          borderColor: 'border-gray-200 dark:border-gray-700',
        };
      default:
        return {
          icon: Clock,
          color: 'text-gray-500 dark:text-gray-500',
          bgColor: 'bg-gray-50 dark:bg-gray-800',
          borderColor: 'border-gray-200 dark:border-gray-700',
        };
    }
  }, [status.status]);

  const StatusIcon = statusConfig.icon;

  return (
    <div className="execution-status-panel space-y-4">
      {costData && (
        <CostWarningBanner
          currentUsage={costData.currentUsage}
          quota={costData.quota}
          estimatedCost={costData.estimatedCost}
          period="day"
          onViewDetails={() => {
            // Navigate to cost monitoring dashboard
            window.location.href = `/settings?tab=governance&section=cost`;
          }}
        />
      )}
      <div className={`p-4 rounded-lg border ${statusConfig.bgColor} ${statusConfig.borderColor}`}>
        <div className="flex items-center gap-3 mb-2">
          <StatusIcon className={`w-5 h-5 ${statusConfig.color} ${status.status === 'RUNNING' ? 'animate-spin' : ''}`} />
          <div className="flex-1">
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {status.message}
            </div>
            {status.detailedMessage && (
              <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                {status.detailedMessage}
              </div>
            )}
          </div>
        </div>

        {status.blockers && status.blockers.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
              Blockers ({status.blockers.length})
            </div>
            <div className="space-y-1">
              {status.blockers.map(blocker => (
                <div
                  key={blocker.id}
                  className="text-xs text-gray-600 dark:text-gray-400 px-2 py-1 bg-white dark:bg-gray-700 rounded"
                >
                  {blocker.reason}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {governanceStatus.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <GovernanceStatusIndicator
            layers={governanceStatus}
            compact={true}
            onViewDetails={() => {
              window.location.href = `/workspaces/${workspaceId}/governance`;
            }}
          />
        </div>
      )}

      {artifacts.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            Execution Artifacts ({artifacts.length})
          </div>
          <div className="space-y-2">
            {artifacts.map(artifact => (
              <div
                key={artifact.id}
                className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                onClick={() => onViewArtifact?.(artifact)}
              >
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {artifact.title || artifact.id}
                </div>
                {artifact.summary && (
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                    {artifact.summary}
                  </div>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                    {artifact.type || 'unknown'}
                  </span>
                  {artifact.file_path && (
                    <span className="text-xs text-gray-500 dark:text-gray-500 truncate flex-1">
                      {artifact.file_path}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {artifacts.length === 0 && status.status === 'UNKNOWN' && (
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">
          No execution status information available
        </div>
      )}
    </div>
  );
}

