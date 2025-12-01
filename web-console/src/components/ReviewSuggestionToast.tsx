/**
 * Review Suggestion Toast Component
 * 顯示回顧建議的 Toast 通知，提供開始整理/略過按鈕
 */

'use client';

import React, { useState, useEffect } from 'react';
import { getReviewSuggestion, recordReviewCompleted, type ReviewSuggestion } from '../lib/review-api';

interface ReviewSuggestionToastProps {
  profileId: string;
  onStartReview?: () => void;
  onDismiss?: () => void;
  autoShow?: boolean; // 是否自動顯示（當有新的建議時）
  checkInterval?: number; // 檢查間隔（毫秒），預設 60 秒
}

export default function ReviewSuggestionToast({
  profileId,
  onStartReview,
  onDismiss,
  autoShow = true,
  checkInterval = 60000, // 60 秒
}: ReviewSuggestionToastProps) {
  const [suggestion, setSuggestion] = useState<ReviewSuggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);

  // 載入回顧建議
  const loadSuggestion = async () => {
    try {
      setLoading(true);
      const data = await getReviewSuggestion(profileId);
      setSuggestion(data);

      // 如果有建議且 autoShow 為 true，顯示
      if (data && autoShow && !visible) {
        setVisible(true);
      }
    } catch (error) {
      console.error('Failed to load review suggestion:', error);
    } finally {
      setLoading(false);
    }
  };

  // 初始載入和定期檢查
  useEffect(() => {
    loadSuggestion();

    if (autoShow) {
      const interval = setInterval(loadSuggestion, checkInterval);
      return () => clearInterval(interval);
    }
  }, [profileId, autoShow, checkInterval]);

  // 處理開始整理
  const handleStartReview = async () => {
    try {
      setLoading(true);

      // 記錄回顧開始（可選）
      // await recordReviewCompleted(profileId);

      // 觸發回調
      onStartReview?.();

      // 隱藏 toast
      setVisible(false);

      // 導航到年度年鑑 Playbook 或顯示回顧頁面
      // 這裡可以導航到 playbook 執行頁面
      window.location.href = '/playbooks/yearly_personal_book';
    } catch (error: any) {
      alert(`開始回顧失敗：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 處理略過
  const handleDismiss = async () => {
    try {
      // 記錄略過（可選，未來可以記錄到後端）
      setVisible(false);
      onDismiss?.();
    } catch (error: any) {
      console.error('Failed to dismiss review:', error);
    }
  };

  // 處理關閉
  const handleClose = () => {
    setVisible(false);
  };

  if (!visible || !suggestion) {
    return null;
  }

  // 計算時間範圍（天數）
  const sinceDate = new Date(suggestion.since);
  const untilDate = new Date(suggestion.until);
  const daysDiff = Math.ceil((untilDate.getTime() - sinceDate.getTime()) / (1000 * 60 * 60 * 24));

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md">
      <div
        className="bg-white rounded-lg shadow-xl border-2 border-blue-200 p-6 animate-slide-up"
        style={{
          animation: 'slideUp 0.3s ease-out',
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-2xl">🧭</span>
            <h3 className="text-lg font-semibold text-gray-900">
              年度回顧建議
            </h3>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Message */}
        <div className="mb-4">
          <p className="text-gray-700 leading-relaxed">
            這{daysDiff > 7 ? '週' : '段期間'}你有 <strong className="text-blue-600">{suggestion.total_entries}</strong> 則記錄，
            其中 <strong className="text-blue-600">{suggestion.insight_events}</strong> 則看起來像值得回頭看的想法，
            要幫你做一個「本週小節」嗎？
          </p>
        </div>

        {/* Stats */}
        <div className="mb-4 p-3 bg-blue-50 rounded-md">
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">總記錄數</span>
            <span className="font-semibold text-gray-900">{suggestion.total_entries}</span>
          </div>
          <div className="flex justify-between text-sm mt-1">
            <span className="text-gray-600">Insight 事件</span>
            <span className="font-semibold text-blue-600">{suggestion.insight_events}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex space-x-3">
          <button
            onClick={handleDismiss}
            disabled={loading}
            className="flex-1 px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            略過
          </button>
          <button
            onClick={handleStartReview}
            disabled={loading}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '處理中...' : '好，開始整理'}
          </button>
        </div>
      </div>

      <style jsx>{`
        @keyframes slideUp {
          from {
            transform: translateY(100%);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        .animate-slide-up {
          animation: slideUp 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
