'use client';

import React, { useState } from 'react';
import { useDriftReport, type DriftReport } from '@/lib/lens-api';

interface LensDriftViewProps {
  profileId: string;
}

export function LensDriftView({ profileId }: LensDriftViewProps) {
  const [days, setDays] = useState(30);
  const { driftReport, isLoading, isError, refresh } = useDriftReport(profileId, days);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>載入漂移分析中...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="h-full flex items-center justify-center text-red-500">
        <p>載入失敗，請重試</p>
      </div>
    );
  }

  if (!driftReport) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>暫無漂移數據</p>
      </div>
    );
  }

  // 处理 node_drift 数据，计算 trigger_rate 和 trend
  const processedNodeDrift = driftReport.node_drift.map((node: any) => {
    const triggerRate = driftReport.total_executions > 0
      ? (node.trigger_count / driftReport.total_executions) * 100
      : 0;

    // 暂时将 trend 设为 'stable'，因为后端没有提供趋势数据
    // 未来可以通过比较不同时间段的数据来计算趋势
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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Lens 漂移分析</h2>
          <p className="text-sm text-gray-600">
            過去 {days} 天，共 {driftReport.total_executions} 次執行
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <label className="text-sm text-gray-600">時間範圍：</label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>7 天</option>
            <option value={30}>30 天</option>
            <option value={90}>90 天</option>
            <option value={180}>180 天</option>
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
          <div className="text-xs text-blue-600 font-medium">總執行次數</div>
          <div className="text-2xl font-bold text-blue-900">{driftReport.total_executions}</div>
        </div>
        <div className="bg-green-50 rounded-lg p-3 border border-green-200">
          <div className="text-xs text-green-600 font-medium">活躍節點</div>
          <div className="text-2xl font-bold text-green-900">{driftReport.node_drift.length}</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
          <div className="text-xs text-purple-600 font-medium">平均觸發率</div>
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

      {/* Node Drift List */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-700">節點觸發趨勢</h3>
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
                        ↗ 上升
                      </span>
                    )}
                    {node.trend === 'decreasing' && (
                      <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded">
                        ↘ 下降
                      </span>
                    )}
                    {node.trend === 'stable' && (
                      <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 rounded">
                        → 穩定
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-4 text-sm">
                  <div className="text-right">
                    <div className="text-gray-500">觸發次數</div>
                    <div className="font-semibold text-gray-900">{node.trigger_count}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-gray-500">觸發率</div>
                    <div className="font-semibold text-gray-900">
                      {node.trigger_rate.toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
              {/* Progress bar */}
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
          <p>暫無節點觸發數據</p>
        </div>
      )}
    </div>
  );
}

