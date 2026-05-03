/**
 * Habit Suggestion Toast Component
 */

'use client';

import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Lightbulb, X } from 'lucide-react';
import { t } from '../lib/i18n';
import { getCandidates, confirmCandidate, rejectCandidate, type HabitCandidateResponse } from '../lib/habits-api';

interface HabitSuggestionToastProps {
  profileId: string;
  onConfirm?: (candidateId: string) => void;
  onReject?: (candidateId: string) => void;
  autoShow?: boolean;
  checkInterval?: number;
}

export default function HabitSuggestionToast({
  profileId,
  onConfirm,
  onReject,
  autoShow = true,
  checkInterval = 30000,
}: HabitSuggestionToastProps) {
  const [candidates, setCandidates] = useState<HabitCandidateResponse[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);

  // Load pending habit candidates.
  const loadCandidates = async () => {
    try {
      setLoading(true);
      const data = await getCandidates(profileId, 'pending', 10);
      setCandidates(data);

      // Show the first pending candidate when auto-show is enabled.
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

  // Load once and then poll on the configured interval.
  useEffect(() => {
    loadCandidates();

    if (autoShow) {
      const interval = setInterval(loadCandidates, checkInterval);
      return () => clearInterval(interval);
    }
  }, [profileId, autoShow, checkInterval]);

  // Confirm the current suggestion.
  const handleConfirm = async () => {
    const candidate = candidates[currentIndex];
    if (!candidate) return;

    try {
      setLoading(true);
      await confirmCandidate(candidate.candidate.id, profileId);

      // Remove the accepted candidate from the list.
      const newCandidates = candidates.filter((_, idx) => idx !== currentIndex);
      setCandidates(newCandidates);

      // Show the next candidate if any remain.
      if (newCandidates.length > 0) {
        setCurrentIndex(Math.min(currentIndex, newCandidates.length - 1));
      } else {
        setVisible(false);
        setCurrentIndex(0);
      }

      onConfirm?.(candidate.candidate.id);

      alert(t('habitConfirmSuccess' as any));
    } catch (error: any) {
      alert(`Confirm failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Reject the current suggestion.
  const handleReject = async () => {
    const candidate = candidates[currentIndex];
    if (!candidate) return;

    try {
      setLoading(true);
      await rejectCandidate(candidate.candidate.id, profileId);

      // Remove the rejected candidate from the list.
      const newCandidates = candidates.filter((_, idx) => idx !== currentIndex);
      setCandidates(newCandidates);

      // Show the next candidate if any remain.
      if (newCandidates.length > 0) {
        setCurrentIndex(Math.min(currentIndex, newCandidates.length - 1));
      } else {
        setVisible(false);
        setCurrentIndex(0);
      }

      onReject?.(candidate.candidate.id);

      alert(t('habitRejectSuccess' as any));
    } catch (error: any) {
      alert(`Reject failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setVisible(false);
  };

  const handleNext = () => {
    if (currentIndex < candidates.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      setVisible(false);
    }
  };

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
    language: t('language' as any) || 'Language',
    communication_style: 'Communication Style',
    response_length: 'Response Length',
    executor_runtime_type: 'Preferred agent type',
    tool_usage: 'Tool Usage',
    playbook_usage: 'Playbook Usage',
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
            <Lightbulb className="h-5 w-5 text-gray-600" aria-hidden="true" />
            <h3 className="text-lg font-semibold text-gray-900">
              {t('habitSuggestions' as any)}
            </h3>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
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
            {t('rejectHabit' as any)}
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {loading ? t('submitting' as any) : t('confirmHabit' as any)}
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
              <span className="inline-flex items-center gap-1">
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </span>
            </button>
            <button
              onClick={handleNext}
              disabled={currentIndex === candidates.length - 1}
              className="text-gray-600 hover:text-gray-700 disabled:text-gray-400 disabled:cursor-not-allowed"
            >
              <span className="inline-flex items-center gap-1">
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </span>
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
