'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import { GraphNodeCreate, GraphNodeUpdate, GraphNode, createNode, updateNode } from '@/lib/graph-api';

interface NodeEditorProps {
  node?: GraphNode;
  onSave: (node: GraphNode) => void;
  onCancel: () => void;
}

export function NodeEditor({ node, onSave, onCancel }: NodeEditorProps) {
  const isEditing = !!node;
  const [formData, setFormData] = useState<any>({
    category: node?.category || 'direction',
    node_type: node?.node_type || 'value',
    label: node?.label || '',
    description: node?.description || '',
    content: node?.content || '',
    icon: node?.icon || '',
    color: node?.color || '',
    size: node?.size || 1.0,
    is_active: node?.is_active ?? true,
    confidence: node?.confidence || 1.0,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (node) {
      setFormData({
        category: node.category,
        node_type: node.node_type,
        label: node.label,
        description: node.description || '',
        content: node.content || '',
        icon: node.icon || '',
        color: node.color || '',
        size: node.size || 1.0,
        is_active: node.is_active ?? true,
        confidence: node.confidence || 1.0,
      });
    } else {
      setFormData({
        category: 'direction',
        node_type: 'value',
        label: '',
        description: '',
        content: '',
        icon: '',
        color: '',
        size: 1.0,
        is_active: true,
        confidence: 1.0,
      });
    }
  }, [node]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      if (isEditing) {
        const updated = await updateNode(node.id, formData as GraphNodeUpdate);
        onSave(updated);
      } else {
        const created = await createNode(formData as GraphNodeCreate);
        onSave(created);
      }
    } catch (err: any) {
      setError(err.message || t('error' as any));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChange = (field: string, value: any) => {
    setFormData((prev: any) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-gray-900">
            {isEditing ? t('graphNodeEditButton' as any) : t('graphNodeCreateButton' as any)}
          </h2>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label={t('close' as any)}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeCategoryLabel' as any)}
              </label>
              <select
                value={formData.category}
                onChange={(e) => handleChange('category', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                required
                disabled={isEditing}
              >
                <option value="direction">{t('graphLensDirection' as any)}</option>
                <option value="action">{t('graphLensAction' as any)}</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeTypeLabel' as any)}
              </label>
              <select
                value={formData.node_type}
                onChange={(e) => handleChange('node_type', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                required
                disabled={isEditing}
              >
                {formData.category === 'direction' ? (
                  <>
                    <option value="value">{t('graphNodeTypeValue' as any)}</option>
                    <option value="worldview">{t('graphNodeTypeWorldview' as any)}</option>
                    <option value="aesthetic">{t('graphNodeTypeAesthetic' as any)}</option>
                    <option value="knowledge">{t('graphNodeTypeKnowledge' as any)}</option>
                  </>
                ) : (
                  <>
                    <option value="strategy">{t('graphNodeTypeStrategy' as any)}</option>
                    <option value="role">{t('graphNodeTypeRole' as any)}</option>
                    <option value="rhythm">{t('graphNodeTypeRhythm' as any)}</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('graphNodeLabelLabel' as any)} *
            </label>
            <input
              type="text"
              value={formData.label}
              onChange={(e) => handleChange('label', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('graphNodeDescriptionLabel' as any)}
            </label>
            <textarea
              value={formData.description || ''}
              onChange={(e) => handleChange('description', e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('graphNodeContentLabel' as any)}
            </label>
            <textarea
              value={formData.content || ''}
              onChange={(e) => handleChange('content', e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeIconLabel' as any)}
              </label>
              <input
                type="text"
                value={formData.icon || ''}
                onChange={(e) => handleChange('icon', e.target.value)}
                placeholder="🎯"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeColorLabel' as any)}
              </label>
              <input
                type="color"
                value={formData.color || '#6366f1'}
                onChange={(e) => handleChange('color', e.target.value)}
                className="w-full h-10 border border-gray-300 rounded-lg cursor-pointer"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeSizeLabel' as any)}
              </label>
              <input
                type="number"
                min="0.1"
                max="5"
                step="0.1"
                value={formData.size}
                onChange={(e) => handleChange('size', parseFloat(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => handleChange('is_active', e.target.checked)}
                  className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-700">{t('graphNodeIsActiveLabel' as any)}</span>
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('graphNodeConfidenceLabel' as any)}
              </label>
              <input
                type="number"
                min="0"
                max="1"
                step="0.1"
                value={formData.confidence}
                onChange={(e) => handleChange('confidence', parseFloat(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              disabled={isSubmitting}
            >
              {t('cancel' as any)}
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting ? t('saving' as any) : (isEditing ? t('save' as any) : t('create' as any))}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

