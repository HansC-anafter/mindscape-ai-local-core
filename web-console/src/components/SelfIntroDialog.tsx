'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';

interface SelfIntroDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { identity: string; solving: string; thinking: string }) => Promise<void>;
}

export default function SelfIntroDialog({ isOpen, onClose, onSubmit }: SelfIntroDialogProps) {
  const [identity, setIdentity] = useState('');
  const [solving, setSolving] = useState('');
  const [thinking, setThinking] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!identity.trim()) {
      alert(t('pleaseCompleteFirstQuestion' as any));
      return;
    }

    try {
      setIsSubmitting(true);
      await onSubmit({ identity, solving, thinking });

      // Reset form
      setIdentity('');
      setSolving('');
      setThinking('');

      onClose();
    } catch (error) {
      console.error('Failed to submit:', error);
      alert(t('submitFailed' as any));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-gray-900">{t('letAIKnowYou' as any)}</h2>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 text-2xl"
              aria-label={t('close' as any)}
            >
              ×
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Question 1 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('whatAreYouMainlyDoing' as any)}？
              </label>
              <input
                type="text"
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                placeholder={t('selfIntroQuestion1Placeholder')}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                disabled={isSubmitting}
              />
            </div>

            {/* Question 2 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('whatDoYouWantToSolve' as any)}？<span className="text-gray-400 text-xs ml-1">（{t('optional' as any)}）</span>
              </label>
              <input
                type="text"
                value={solving}
                onChange={(e) => setSolving(e.target.value)}
                placeholder={t('selfIntroQuestion2Placeholder')}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                disabled={isSubmitting}
              />
            </div>

            {/* Question 3 */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t('whatAreYouThinking' as any)}？<span className="text-gray-400 text-xs ml-1">（{t('optional' as any)}）</span>
              </label>
              <input
                type="text"
                value={thinking}
                onChange={(e) => setThinking(e.target.value)}
                placeholder={t('selfIntroQuestion3Placeholder')}
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-gray-500 focus:border-transparent"
                disabled={isSubmitting}
              />
            </div>

            {/* Helper text */}
            <p className="text-sm text-gray-500 mb-6">
              {t('selfIntroHelperText' as any)}
            </p>

            {/* Actions */}
            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                className="px-6 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 disabled:opacity-50"
                disabled={isSubmitting}
              >
                {t('cancel' as any)}
              </button>
              <button
                type="submit"
                className="px-6 py-2 text-white bg-gray-600 rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isSubmitting}
              >
                {isSubmitting ? t('submitting' as any) : t('completeSetup' as any)}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
