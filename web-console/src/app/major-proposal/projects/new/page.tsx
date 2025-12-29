'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../../components/Header';
import { t } from '@/lib/i18n';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

interface ProposalTemplate {
  id: string;
  name: string;
  template_type: string;
}

export default function NewProjectPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [templates, setTemplates] = useState<ProposalTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>(
    searchParams?.get('template_id') || ''
  );
  const [projectName, setProjectName] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/templates`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      } else {
        throw new Error('Failed to load templates');
      }
    } catch (err: any) {
      console.error('Failed to load templates:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTemplateId) {
      alert(t('majorProposalSelectTemplate'));
      return;
    }
    if (!projectName.trim()) {
      alert(t('majorProposalEnterProjectName'));
      return;
    }

    try {
      setCreating(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const formData = new FormData();
      formData.append('template_id', selectedTemplateId);
      formData.append('project_name', projectName.trim());
      formData.append('profile_id', 'default-user');

      const response = await fetch(`${apiUrl}/api/v1/proposal/projects`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        router.push(`/major-proposal/projects/${result.project_id}`);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create project');
      }
    } catch (err: any) {
      console.error('Failed to create project:', err);
      alert(t('majorProposalCreateProjectFailed', { error: err.message }));
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="text-center">載入中...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <div className="mb-6">
          <Link href="/major-proposal" className="text-blue-600 hover:underline mb-2 inline-block">
            ← 返回
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">建立新申請文件專案</h1>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              選擇模板 <span className="text-red-500">*</span>
            </label>
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              required
            >
              <option value="">請選擇模板</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name} ({template.template_type})
                </option>
              ))}
            </select>
            {templates.length === 0 && (
              <p className="mt-2 text-sm text-gray-500">
                尚無模板，請先{' '}
                <Link href="/major-proposal" className="text-blue-600 hover:underline">
                  上傳模板
                </Link>
              </p>
            )}
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              專案名稱 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder={t('majorProposalEnterProjectNamePlaceholder')}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              required
            />
          </div>

          <div className="flex justify-end space-x-3">
            <Link
              href="/major-proposal"
              className="px-4 py-2 border border-gray-300 rounded text-gray-700 hover:bg-gray-50"
            >
              取消
            </Link>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={creating || !selectedTemplateId || !projectName.trim()}
            >
              {creating ? t('majorProposalCreating') : t('majorProposalCreateProject')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
