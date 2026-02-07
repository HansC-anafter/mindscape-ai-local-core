'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';

interface CopyVariantModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (variantName: string, variantDescription: string) => void;
  playbookName: string;
}

export default function CopyVariantModal({
  isOpen,
  onClose,
  onConfirm,
  playbookName
}: CopyVariantModalProps) {
  const [variantName, setVariantName] = useState('');
  const [variantDescription, setVariantDescription] = useState('');

  if (!isOpen) return null;

  const handleSubmit = () => {
    if (!variantName.trim()) {
      alert(t('playbookEnterVariantName' as any));
      return;
    }
    onConfirm(variantName, variantDescription);
    setVariantName('');
    setVariantDescription('');
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-surface-accent dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-primary dark:text-gray-100">{t('createMyVersion' as any)}</h2>
          <button
            onClick={onClose}
            className="text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-300 text-2xl"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
              {t('variantName' as any)}
            </label>
            <input
              type="text"
              value={variantName}
              onChange={(e) => setVariantName(e.target.value)}
              placeholder={t('myVersionPlaceholder', { name: playbookName })}
              className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent dark:focus:ring-blue-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
              autoFocus
              autoComplete="off"
              data-lpignore="true"
              data-form-type="other"
              data-1p-ignore="true"
              name="copy-variant-name-input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-1">
              {t('descriptionOptional' as any)}
            </label>
            <textarea
              value={variantDescription}
              onChange={(e) => setVariantDescription(e.target.value)}
              placeholder={t('variantNameExample' as any)}
              rows={3}
              className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent dark:focus:ring-blue-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
              autoComplete="off"
              data-lpignore="true"
              data-form-type="other"
              data-1p-ignore="true"
              name="copy-variant-description-input"
            />
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm text-primary dark:text-gray-300 hover:text-primary dark:hover:text-gray-100 border border-default dark:border-gray-600 rounded-md hover:bg-surface-secondary dark:hover:bg-gray-700"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 px-4 py-2 text-sm bg-accent dark:bg-blue-600 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-700"
          >
            建立
          </button>
        </div>
      </div>
    </div>
  );
}
