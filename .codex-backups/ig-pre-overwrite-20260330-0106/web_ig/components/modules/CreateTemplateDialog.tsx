'use client';

/**
 * Create Template Dialog
 */

import React, { useState, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { X } from 'lucide-react';

interface InteractionTemplate {
  template_id: string;
  template_type: 'comment_reply' | 'dm_script' | 'story_reply';
  content: string;
  tone: 'formal' | 'casual' | 'friendly' | 'professional' | 'humorous';
  category: string;
  tags: string[];
  variables?: string[];
}

interface CreateTemplateDialogProps {
  workspaceId: string;
  apiUrl: string;
  template?: InteractionTemplate | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateTemplateDialog({
  workspaceId,
  apiUrl,
  template,
  onClose,
  onSuccess
}: CreateTemplateDialogProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [templateId, setTemplateId] = useState(template?.template_id || '');
  const [templateType, setTemplateType] = useState<InteractionTemplate['template_type']>(template?.template_type || 'comment_reply');
  const [content, setContent] = useState(template?.content || '');
  const [tone, setTone] = useState<InteractionTemplate['tone']>(template?.tone || 'friendly');
  const [category, setCategory] = useState(template?.category || '');
  const [tags, setTags] = useState(template?.tags?.join(', ') || '');
  const [variables, setVariables] = useState(template?.variables?.join(', ') || '');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!templateId.trim() || !content.trim()) {
      alert('Please fill in template ID and content');
      return;
    }

    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_interaction_templates',
        inputs: {
          action: template ? 'update' : 'create',
          workspace_id: workspaceId,
          template_id: templateId,
          template_type: templateType,
          content: content,
          tone: tone,
          category: category || undefined,
          tags: tags.split(',').map(t => t.trim()).filter(t => t.length > 0),
          variables: variables.split(',').map(v => v.trim()).filter(v => v.length > 0)
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        onSuccess();
      } else {
        const error = await response.json();
        alert(`Operation failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to save template:', err);
      alert(`Operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Template ID *
        </label>
        <input
          type="text"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          disabled={!!template}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          placeholder="e.g., welcome_reply"
        />
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Template Type *
        </label>
        <select
          value={templateType}
          onChange={(e) => setTemplateType(e.target.value as typeof templateType)}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
        >
          <option value="comment_reply">Comment Reply</option>
          <option value="dm_script">DM Script</option>
          <option value="story_reply">Story Reply</option>
        </select>
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Content *
        </label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          placeholder="Template content, use {{variable}} for variables"
        />
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Tone *
        </label>
        <select
          value={tone}
          onChange={(e) => setTone(e.target.value as typeof tone)}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
        >
          <option value="formal">Formal</option>
          <option value="casual">Casual</option>
          <option value="friendly">Friendly</option>
          <option value="professional">Professional</option>
          <option value="humorous">Humorous</option>
        </select>
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Category
        </label>
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          placeholder="e.g., welcome, thanks, inquiry"
        />
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Tags (comma-separated)
        </label>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          placeholder="e.g., welcome, first-time, faq"
        />
      </div>

      <div>
        <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
          Variables (comma-separated)
        </label>
        <input
          type="text"
          value={variables}
          onChange={(e) => setVariables(e.target.value)}
          className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          placeholder="e.g., username, product_name"
        />
      </div>

      <div className="flex items-center gap-2 pt-4">
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Saving...' : template ? 'Update' : 'Create'}
        </button>
        <button
          onClick={onClose}
          className="flex-1 px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
