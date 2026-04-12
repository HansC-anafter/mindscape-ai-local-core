'use client';

/**
 * Export Panel
 *
 * Features:
 * - Export pack generation panel
 * - Export content preview
 * - Export history
 */

import React, { useState, useEffect, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { Download, FileText, CheckCircle2, Clock, Eye } from 'lucide-react';
import type { IGPost } from '../types';

interface ExportPanelProps {
  workspaceId: string;
  apiUrl: string;
  selectedPostId: string | null;
  posts: IGPost[];
}

interface ExportPack {
  post_path: string;
  export_id: string;
  exported_at: string;
  files: Array<{
    name: string;
    content: string;
    type: 'markdown' | 'text' | 'json';
  }>;
}

export default function ExportPanel({
  workspaceId,
  apiUrl,
  selectedPostId,
  posts
}: ExportPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [exportHistory, setExportHistory] = useState<ExportPack[]>([]);
  const [selectedExport, setSelectedExport] = useState<ExportPack | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);

  useEffect(() => {
    loadExportHistory();
  }, [workspaceId, apiUrl]);

  const loadExportHistory = async () => {
    setLoading(true);
    try {
      const response = await client.get(
        `/api/v1/workspaces/${workspaceId}/executions?playbook_code_prefix=ig_export_pack_generator&limit=50&order_by=created_at&order=desc`
      );

      if (!response.ok) {
        throw new Error('Failed to load export history');
      }

      const data = await response.json();
      const exports: ExportPack[] = (data.executions || [])
        .filter((exec: any) => exec.status === 'completed')
        .map((exec: any) => {
          const result = exec.result || {};
          const inputs = exec.inputs || {};

          const filesGenerated = result.files_generated || [];
          const exportPackData = result.export_pack || {};

          const files = filesGenerated.map((filePath: string) => {
            const fileName = filePath.split('/').pop() || filePath;
            let content = '';
            if (fileName === 'post.md' || fileName.includes('post.md')) {
              content = exportPackData.post_md || '';
            } else if (fileName === 'hashtags.txt' || fileName.includes('hashtags.txt')) {
              content = exportPackData.hashtags_txt || '';
            } else if (fileName === 'cta_variants.txt' || fileName.includes('cta_variants.txt')) {
              content = exportPackData.cta_variants_txt || '';
            } else if (fileName === 'checklist.md' || fileName.includes('checklist.md')) {
              content = exportPackData.checklist_md || '';
            } else if (exportPackData[fileName]) {
              content = typeof exportPackData[fileName] === 'string'
                ? exportPackData[fileName]
                : JSON.stringify(exportPackData[fileName], null, 2);
            }

            return {
              name: fileName,
              content: content,
              type: filePath.endsWith('.md') ? 'markdown' :
                filePath.endsWith('.txt') ? 'text' :
                  filePath.endsWith('.json') ? 'json' : 'text'
            };
          });

          return {
            post_path: result.post_path || inputs.post_path || 'unknown',
            export_id: exec.id,
            exported_at: exec.completed_at || exec.updated_at || exec.created_at,
            files: files
          };
        });

      setExportHistory(exports);
    } catch (err) {
      console.error('Failed to load export history:', err);
      setExportHistory([]);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateExport = async () => {
    if (!selectedPostId) {
      alert('Please select a post first');
      return;
    }

    setLoading(true);
    try {
      const post = posts.find(p => p.id === selectedPostId);
      if (!post) {
        throw new Error('Selected post does not exist');
      }

      if (!post.post_path) {
        throw new Error(`Post ${post.id} missing post_path. Cannot generate export pack. Please ensure post has a valid file path.`);
      }

      const response = await client.post(`/api/v1/playbooks/execute`, {
        playbook_code: 'ig_export_pack_generator',
        inputs: {
          workspace_id: workspaceId,
          post_path: post.post_path
        },
        execution_mode: 'sync'
      });

      if (response.ok) {
        const data = await response.json();
        const result = data.result || {};
        const filesGenerated = result.files_generated || [];
        const exportPackData = result.export_pack || {};

        const files = filesGenerated.map((filePath: string) => {
          const fileName = filePath.split('/').pop() || filePath;
          let content = '';
          if (fileName === 'post.md' || fileName.endsWith('post.md')) {
            content = exportPackData.post_md || '';
          } else if (fileName === 'hashtags.txt' || fileName.endsWith('hashtags.txt')) {
            content = exportPackData.hashtags_txt || '';
          } else if (fileName === 'cta_variants.txt' || fileName.endsWith('cta_variants.txt')) {
            content = exportPackData.cta_variants_txt || '';
          } else if (fileName === 'checklist.md' || fileName.endsWith('checklist.md')) {
            content = exportPackData.checklist_md || '';
          } else if (exportPackData[fileName]) {
            content = typeof exportPackData[fileName] === 'string'
              ? exportPackData[fileName]
              : JSON.stringify(exportPackData[fileName], null, 2);
          }

          return {
            name: fileName,
            content: content,
            type: filePath.endsWith('.md') ? 'markdown' :
              filePath.endsWith('.txt') ? 'text' :
                filePath.endsWith('.json') ? 'json' : 'text'
          };
        });

        const exportPack: ExportPack = {
          post_path: post.post_path,
          export_id: data.execution_id || Date.now().toString(),
          exported_at: new Date().toISOString(),
          files: files
        };

        setExportHistory([exportPack, ...exportHistory]);
        setSelectedExport(exportPack);
        alert('Export pack generated successfully!');
      } else {
        const error = await response.json();
        alert(`Export failed: ${error.detail || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to generate export pack:', err);
      alert(`Export failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const handlePreviewFile = (file: ExportPack['files'][0]) => {
    setPreviewContent(file.content);
  };

  const handleDownloadFile = (file: ExportPack['files'][0], exportId: string) => {
    const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.name;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (selectedExport && previewContent !== null) {
    const file = selectedExport.files.find(f => f.content === previewContent);
    return (
      <div className="h-full flex flex-col p-4">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => setPreviewContent(null)}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            Back to Export Details
          </button>
        </div>
        <div className="flex-1 overflow-y-auto bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {file?.name || 'Preview'}
            </h3>
            {file && (
              <button
                onClick={() => handleDownloadFile(file, selectedExport.export_id)}
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
              >
                <Download className="w-3.5 h-3.5" />
                Download
              </button>
            )}
          </div>
          <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono">
            {previewContent}
          </pre>
        </div>
      </div>
    );
  }

  if (selectedExport) {
    return (
      <div className="h-full flex flex-col p-4">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={() => setSelectedExport(null)}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            Back to Export List
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
              Export Pack Details
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {selectedExport.post_path}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Exported at: {new Date(selectedExport.exported_at).toLocaleString()}
            </p>
          </div>

          {/* Export files list */}
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
              Export Files ({selectedExport.files.length})
            </h3>
            <div className="space-y-2">
              {selectedExport.files.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="w-4 h-4 text-gray-400" />
                    <div>
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {file.name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {file.type}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handlePreviewFile(file)}
                      className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                      title="Preview"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDownloadFile(file, selectedExport.export_id)}
                      className="p-2 text-gray-400 hover:text-green-600 dark:hover:text-green-400"
                      title="Download"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          Export Pack Generation
        </h2>
        <button
          onClick={handleGenerateExport}
          disabled={loading || !selectedPostId}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Generate Export Pack
        </button>
      </div>

      {!selectedPostId && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3 mb-4">
          <p className="text-sm text-yellow-800 dark:text-yellow-300">
            Please select a post in Grid View first.
          </p>
        </div>
      )}

      {/* Export history */}
      <div className="flex-1 overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Export History
        </h3>
        <div className="space-y-2">
          {exportHistory.length === 0 ? (
            <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
              No export records
            </div>
          ) : (
            exportHistory.map((exportPack) => (
              <div
                key={exportPack.export_id}
                onClick={() => setSelectedExport(exportPack)}
                className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 cursor-pointer transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {exportPack.post_path}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {exportPack.files.length} file{exportPack.files.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Exported at: {new Date(exportPack.exported_at).toLocaleString()}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
