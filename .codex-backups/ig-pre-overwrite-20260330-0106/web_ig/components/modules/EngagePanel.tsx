'use client';

/**
 * Engage Panel
 *
 * Features:
 * - Interaction template management panel
 * - Comment reply templates
 * - DM script templates
 * - Tone switching and categorization
 */

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { MessageSquare, Plus, Search, Copy, Edit, Trash2, Tag } from 'lucide-react';
import CreateTemplateDialog from './CreateTemplateDialog';

interface EngagePanelProps {
  workspaceId: string;
  apiUrl: string;
}

interface InteractionTemplate {
  template_id: string;
  template_type: 'comment_reply' | 'dm_script' | 'story_reply';
  content: string;
  tone: 'formal' | 'casual' | 'friendly' | 'professional' | 'humorous';
  category: string;
  tags: string[];
  variables?: string[];
  created_at: string;
  updated_at: string;
}

export default function EngagePanel({
  workspaceId,
  apiUrl
}: EngagePanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [templates, setTemplates] = useState<InteractionTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<InteractionTemplate | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'comment_reply' | 'dm_script' | 'story_reply'>('all');
  const [filterTone, setFilterTone] = useState<'all' | 'formal' | 'casual' | 'friendly' | 'professional' | 'humorous'>('all');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<InteractionTemplate | null>(null);
  const [renderedContent, setRenderedContent] = useState<string | null>(null);

  useEffect(() => {
    loadTemplates();
  }, [workspaceId, apiUrl]);

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_interaction_templates',
        inputs: {
          action: 'list',
          workspace_id: workspaceId,
          template_type: filterType !== 'all' ? filterType : undefined,
          tone: filterTone !== 'all' ? filterTone : undefined
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        setTemplates(data.result?.templates || []);
      }
    } catch (err) {
      console.error('Failed to load templates:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, [filterType, filterTone]);

  const handleRenderTemplate = async (templateId: string, variables: Record<string, string>) => {
    setLoading(true);
    try {
      const response = await client.post('/api/v1/playbooks/execute', {
        playbook_code: 'ig_interaction_templates',
        inputs: {
          action: 'render',
          workspace_id: workspaceId,
          template_id: templateId,
          render_variables: variables
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        setRenderedContent(data.result?.rendered_content || null);
      }
    } catch (err) {
      console.error('Failed to render template:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyTemplate = (content: string) => {
    navigator.clipboard.writeText(content);
    alert('Copied to clipboard');
  };

  const filteredTemplates = templates.filter(template => {
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        template.content.toLowerCase().includes(query) ||
        template.category.toLowerCase().includes(query) ||
        template.tags.some(tag => tag.toLowerCase().includes(query))
      );
    }
    return true;
  });

  const getToneColor = (tone: string): string => {
    switch (tone) {
      case 'formal':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400';
      case 'casual':
        return 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400';
      case 'friendly':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400';
      case 'professional':
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900/20 dark:text-purple-400';
      case 'humorous':
        return 'bg-pink-100 text-pink-800 dark:bg-pink-900/20 dark:text-pink-400';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
  };

  const getTypeLabel = (type: string): string => {
    switch (type) {
      case 'comment_reply':
        return 'Comment Reply';
      case 'dm_script':
        return 'DM Script';
      case 'story_reply':
        return 'Story Reply';
      default:
        return type;
    }
  };

  if (selectedTemplate) {
    return (
      <div className="h-full flex flex-col p-4">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => setSelectedTemplate(null)}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            Back to Template List
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
              {selectedTemplate.template_id}
            </h2>
            <div className="flex items-center gap-2 mb-4">
              <span className={`px-2 py-1 text-xs rounded ${getToneColor(selectedTemplate.tone)}`}>
                {selectedTemplate.tone}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {getTypeLabel(selectedTemplate.template_type)}
              </span>
            </div>
          </div>

          {/* Template content */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Template Content
              </h3>
              <button
                onClick={() => handleCopyTemplate(selectedTemplate.content)}
                className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                title="Copy"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {selectedTemplate.content}
            </p>
          </div>

          {/* Variables */}
          {selectedTemplate.variables && selectedTemplate.variables.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Available Variables
              </h3>
              <div className="flex flex-wrap gap-2">
                {selectedTemplate.variables.map((variable, index) => (
                  <span
                    key={index}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
                  >
                    {`{{${variable}}}`}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tags */}
          {selectedTemplate.tags && selectedTemplate.tags.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Tags
              </h3>
              <div className="flex flex-wrap gap-2">
                {selectedTemplate.tags.map((tag, index) => (
                  <span
                    key={index}
                    className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900/20 text-blue-800 dark:text-blue-300 rounded flex items-center gap-1"
                  >
                    <Tag className="w-3 h-3" />
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Rendered result */}
          {renderedContent && (
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800 p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-green-900 dark:text-green-100">
                  Rendered Result
                </h3>
                <button
                  onClick={() => handleCopyTemplate(renderedContent)}
                  className="p-2 text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300"
                  title="Copy"
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm text-green-800 dark:text-green-300 whitespace-pre-wrap">
                {renderedContent}
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          Interaction Templates
        </h2>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus className="w-3.5 h-3.5" />
          New Template
        </button>
      </div>

      {/* Search and filters */}
      <div className="mb-4 space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search templates..."
            className="w-full pl-10 pr-4 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as typeof filterType)}
            className="px-3 py-1.5 text-xs border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="all">All Types</option>
            <option value="comment_reply">Comment Reply</option>
            <option value="dm_script">DM Script</option>
            <option value="story_reply">Story Reply</option>
          </select>
          <select
            value={filterTone}
            onChange={(e) => setFilterTone(e.target.value as typeof filterTone)}
            className="px-3 py-1.5 text-xs border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="all">All Tones</option>
            <option value="formal">Formal</option>
            <option value="casual">Casual</option>
            <option value="friendly">Friendly</option>
            <option value="professional">Professional</option>
            <option value="humorous">Humorous</option>
          </select>
        </div>
      </div>

      {/* Template list */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            Loading templates...
          </div>
        ) : filteredTemplates.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
            {searchQuery ? 'No matching templates found' : 'No templates. Click "New Template" to create'}
          </div>
        ) : (
          filteredTemplates.map((template) => (
            <div
              key={template.template_id}
              className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
            >
              <div
                onClick={() => setSelectedTemplate(template)}
                className="cursor-pointer"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
                      {template.template_id}
                    </h3>
                    <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-2">
                      {template.content}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <span className={`px-2 py-0.5 text-xs rounded ${getToneColor(template.tone)}`}>
                    {template.tone}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {getTypeLabel(template.template_type)}
                  </span>
                  {template.tags && template.tags.length > 0 && (
                    <div className="flex items-center gap-1">
                      {template.tags.slice(0, 3).map((tag, index) => (
                        <span
                          key={index}
                          className="px-1.5 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                      {template.tags.length > 3 && (
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          +{template.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingTemplate(template);
                    setShowCreateDialog(true);
                  }}
                  className="px-2 py-1 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                >
                  <Edit className="w-3 h-3 inline mr-1" />
                  Edit
                </button>
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (confirm('Are you sure you want to delete this template?')) {
                      setLoading(true);
                      try {
                        const response = await client.post('/api/v1/playbooks/execute', {
                          playbook_code: 'ig_interaction_templates',
                          inputs: {
                            action: 'delete',
                            workspace_id: workspaceId,
                            template_id: template.template_id
                          },
                          execution_mode: 'sync'
                        });
                        if (response.ok) {
                          await loadTemplates();
                        } else {
                          alert('Delete failed');
                        }
                      } catch (err) {
                        console.error('Failed to delete template:', err);
                        alert('Delete failed');
                      } finally {
                        setLoading(false);
                      }
                    }
                  }}
                  className="px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                >
                  <Trash2 className="w-3 h-3 inline mr-1" />
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Create/Edit dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
              {editingTemplate || selectedTemplate ? 'Edit Template' : 'New Template'}
            </h3>
            <CreateTemplateDialog
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              template={editingTemplate || selectedTemplate}
              onClose={() => {
                setShowCreateDialog(false);
                setSelectedTemplate(null);
                setEditingTemplate(null);
              }}
              onSuccess={() => {
                setShowCreateDialog(false);
                setSelectedTemplate(null);
                setEditingTemplate(null);
                loadTemplates();
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
