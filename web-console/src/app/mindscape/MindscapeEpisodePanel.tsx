import React from 'react';
import { formatLocalDateTime } from '@/lib/time';
import type { MindscapeIntent } from './mindscapePageTypes';

interface MindscapeEpisodePanelProps {
  intents: MindscapeIntent[];
  onStartDailyPlanning: () => void;
  onStartContentDrafting: () => void;
  onStartSystemCheck: () => void;
  onContinueIntent: (intent: MindscapeIntent) => void;
  onDirectEntry: () => void;
}

export function MindscapeEpisodePanel({
  intents,
  onStartDailyPlanning,
  onStartContentDrafting,
  onStartSystemCheck,
  onContinueIntent,
  onDirectEntry,
}: MindscapeEpisodePanelProps) {
  return (
    <div className="mb-8">
      <div className="bg-gradient-to-r from-gray-50 to-blue-50 border-2 border-gray-200 rounded-lg p-8 mb-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">歡迎回到你的 Mindscape AI 工作站</h2>
        <div className="text-gray-600 mb-6">先選一個今天要啟動的模式，AI 團隊就會照這個方向配合你工作。</div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <button
            onClick={onStartDailyPlanning}
            className="p-6 bg-white rounded-lg border-2 border-blue-200 hover:border-blue-400 hover:shadow-lg transition-all text-left"
          >
            <div className="text-3xl mb-3">🗓</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">今天先把事情排好</h3>
            <p className="text-sm text-gray-600">收集任務 → 排優先順序 → 形成今日 checklist</p>
          </button>

          <button
            onClick={onStartContentDrafting}
            className="p-6 bg-white rounded-lg border-2 border-green-200 hover:border-green-400 hover:shadow-lg transition-all text-left"
          >
            <div className="text-3xl mb-3">✍️</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">我想寫一份內容</h3>
            <p className="text-sm text-gray-600">理解需求 → 設計結構 → 出草稿</p>
          </button>

          <button
            onClick={onStartSystemCheck}
            className="p-6 bg-white rounded-lg border-2 border-yellow-200 hover:border-yellow-400 hover:shadow-lg transition-all text-left"
          >
            <div className="text-3xl mb-3">🔧</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">先讓默默 AI 幫我檢查系統</h3>
            <p className="text-sm text-gray-600">檢查設定、工具連接、系統健康狀態</p>
          </button>
        </div>

        {intents.length > 0 && (
          <div className="mb-4 p-4 bg-white rounded-lg border border-gray-200">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">繼續上次主線</h3>
            <div className="space-y-2">
              {intents.slice(0, 2).map((intent) => (
                <button
                  key={intent.id}
                  onClick={() => onContinueIntent(intent)}
                  className="w-full text-left p-3 bg-gray-50 hover:bg-gray-100 rounded border border-gray-200 transition-colors"
                >
                  <div className="font-medium text-gray-900">{intent.title}</div>
                  <div className="text-xs text-gray-500 mt-1">上次更新：{formatLocalDateTime(intent.updated_at)}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="text-right">
          <button
            onClick={onDirectEntry}
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            直接進工作站 →
          </button>
        </div>
      </div>
    </div>
  );
}
