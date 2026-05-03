'use client';

import React, { useState } from 'react';
import { useDriftReport } from '@/lib/lens-api';

interface LensDriftViewProps {
  profileId: string;
}

export function LensDriftView({ profileId }: LensDriftViewProps) {
  const [days, setDays] = useState(30);
  const { driftReport, isLoading, isError } = useDriftReport(profileId, days);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>Loading drift analysis...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full flex items-center justify-center text-red-500">
        <p>Failed to load. Try again.</p>
      </div>
    );
  }

  if (!driftReport) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No drift data</p>
      </div>
    );
  }

  const processedNodeDrift = driftReport.node_drift.map((node: any) => {
    const triggerRate = driftReport.total_executions > 0
      ? (node.trigger_count / driftReport.total_executions) * 100
      : 0;

    const trend: string = 'stable';

    return {
      node_id: node.node_id,
      node_label: node.node_label,
      trigger_count: node.trigger_count,
      trigger_rate: triggerRate,
      trend,
    };
  });

  const sortedNodeDrift = [...processedNodeDrift].sort(
    (a, b) => b.trigger_count - a.trigger_count
  );

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Lens Drift Analysis</h2>
          <p className="text-sm text-gray-600">
            Past {days} days, {driftReport.total_executions} executions
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <label className="text-sm text-gray-600">Time Range:</label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
          <div className="text-xs text-blue-600 font-medium">Total Executions</div>
          <div className="text-2xl font-bold text-blue-900">{driftReport.total_executions}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-3 border border-green-200">
          <div className="text-xs text-green-600 font-medium">Active Nodes</div>
          <div className="text-2xl font-bold text-green-900">{driftReport.node_drift.length}</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
          <div className="text-xs text-purple-600 font-medium">Average Trigger Rate</div>
          <div className="text-2xl font-bold text-purple-900">
            {processedNodeDrift.length > 0
              ? (
                processedNodeDrift.reduce((sum, node) => sum + node.trigger_rate, 0) /
                processedNodeDrift.length
              ).toFixed(1)
              : '0.0'}
            %
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-700">Node Trigger Trends</h3>
        <div className="space-y-2">
          {sortedNodeDrift.map((node) => (
            <div
              key={node.node_id}
              className="bg-white rounded-lg p-3 border border-gray-200 hover:border-gray-300 transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-gray-900">{node.node_label}</span>
                    {node.trend === 'increasing' && (
                      <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
                        Increasing
                      </span>
                    )}
                    {node.trend === 'decreasing' && (
                      <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded">
                        Decreasing
                      </span>
                    )}
                    {node.trend === 'stable' && (
                      <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 rounded">
                        Stable
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-4 text-sm">
                  <div className="text-right">
                    <div className="text-gray-500">Trigger Count</div>
                    <div className="font-semibold text-gray-900">{node.trigger_count}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-gray-500">Trigger Rate</div>
                    <div className="font-semibold text-gray-900">
                      {node.trigger_rate.toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-2">
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${node.trend === 'increasing'
                        ? 'bg-green-500'
                        : node.trend === 'decreasing'
                          ? 'bg-red-500'
                          : 'bg-gray-500'
                      }`}
                    style={{ width: `${Math.min(node.trigger_rate, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {sortedNodeDrift.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <p>No node trigger data</p>
        </div>
      )}
    </div>
  );
}
