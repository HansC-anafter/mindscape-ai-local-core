/**
 * Habit Suggestion Toast Component
 * 顯示習慣建議的 Toast 通知，提供確認/拒絕按鈕
 */

'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../lib/i18n';
import { getCandidates, confirmCandidate, rejectCandidate, type HabitCandidateResponse } from '../lib/habits-api';

interface HabitSuggestionToastProps {
  profileId: string;
  onConfirm?: (candidateId: string) => void;
  onReject?: (candidateId: string) => void;
  autoShow?: boolean; // 是否自動顯示（當有新的候選時）
  checkInterval?: number; // 檢查間隔（毫秒），預設 30 秒
}

export default function HabitSuggestionToast({
  profileId,
  onConfirm,
  onReject,
  autoShow = true,
  checkInterval = 30000, // 30 秒
}: HabitSuggestionToastProps) {
  const [candidates, setCandidates] = useState<HabitCandidateResponse[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);

  // 載入候選習慣
  const loadCandidates = async () => {
    try {
      setLoading(true);
      const data = await getCandidates(profileId, 'pending', 10);
      setCandidates(data);
      
      // 如果有新的候選且 autoShow 為 true，顯示第一個
      if (data.length > 0 && autoShow && !visible) {
        setCurrentIndex(0);
        setVisible(true);
      }
    } catch (error) {
      console.error('Failed to load habit candidates:', error);
    } finally {
      setLoading(false);
    }
  };

  // 初始載入和定期檢查
  useEffect(() => {
    loadCandidates();
    
    if (autoShow) {
      const interval = setInterval(loadCandidates, checkInterval);
      return () => clearInterval(interval);
    }
  }, [profileId, autoShow, checkInterval]);

  // 處理確認
  const handleConfirm = async () => {
    const candidate = candidates[currentIndex];
    if (!candidate) return;

    try {
      setLoading(true);
      await confirmCandidate(candidate.candidate.id, profileId);
      
      // 從列表中移除
      const newCandidates = candidates.filter((_, idx) => idx !== currentIndex);
      setCandidates(newCandidates);
      
      // 如果有下一個，顯示下一個；否則隱藏
      if (newCandidates.length > 0) {
        setCurrentIndex(Math.min(currentIndex, newCandidates.length - 1));
      } else {
        setVisible(false);
        setCurrentIndex(0);
      }

      onConfirm?.(candidate.candidate.id);
      
      // 顯示成功訊息
      alert(t('habitConfirmSuccess'));
    } catch (error: any) {
      alert(`確認失敗：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 處理拒絕
  const handleReject = async () => {
    const candidate = candidates[currentIndex];
    if (!candidate) return;

    try {
      setLoading(true);
      await rejectCandidate(candidate.candidate.id, profileId);
      
      // 從列表中移除
      const newCandidates = candidates.filter((_, idx) => idx !== currentIndex);
      setCandidates(newCandidates);
      
      // 如果有下一個，顯示下一個；否則隱藏
      if (newCandidates.length > 0) {
        setCurrentIndex(Math.min(currentIndex, newCandidates.length - 1));
      } else {
        setVisible(false);
        setCurrentIndex(0);
      }

      onReject?.(candidate.candidate.id);
      
      // 顯示成功訊息
      alert(t('habitRejectSuccess'));
    } catch (error: any) {
      alert(`拒絕失敗：${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // 處理關閉
  const handleClose = () => {
    setVisible(false);
  };

  // 處理下一個
  const handleNext = () => {
    if (currentIndex < candidates.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setVisible(false);
    }
  };

  // 處理上一個
  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  if (!visible || candidates.length === 0) {
    return null;
  }

  const candidate = candidates[currentIndex];
  if (!candidate) {
    return null;
  }

  const habitKeyDisplay: Record<string, string> = {
    language: t('language') || '語言',
    communication_style: '溝通風格',
    response_length: '回應長度',
    preferred_agent_type: '偏好的 Agent 類型',
    tool_usage: '工具使用',
    playbook_usage: 'Playbook 使用',
  };

  const habitKey = habitKeyDisplay[candidate.candidate.habit_key] || candidate.candidate.habit_key;
  const confidencePercent = Math.round(candidate.candidate.confidence * 100);

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md">
      <div
        className="bg-white rounded-lg shadow-xl border-2 border-gray-200 p-6 animate-slide-up"
        style={{
          animation: 'slideUp 0.3s ease-out',
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-2xl">💡</span>
            <h3 className="text-lg font-semibold text-gray-900">
              {t('habitSuggestions')}
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
            {candidate.suggestion_message}
          </p>
        </div>

        {/* Progress indicator */}
        {candidates.length > 1 && (
          <div className="mb-4 text-sm text-gray-500">
            {currentIndex + 1} / {candidates.length}
          </div>
        )}

        {/* Actions */}
        <div className="flex space-x-3">
          <button
            onClick={handleReject}
            disabled={loading}
            className="flex-1 px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {t('rejectHabit')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {loading ? t('submitting') : t('confirmHabit')}
          </button>
        </div>

        {/* Navigation (if multiple candidates) */}
        {candidates.length > 1 && (
          <div className="mt-4 flex justify-between items-center text-sm">
            <button
              onClick={handlePrevious}
              disabled={currentIndex === 0}
              className="text-gray-600 hover:text-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
              ← 上一個
            </button>
            <button
              onClick={handleNext}
              disabled={currentIndex === candidates.length - 1}
              className="text-gray-600 hover:text-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
              下一個 →
            </button>
          </div>
        )}
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
