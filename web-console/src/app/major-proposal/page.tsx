'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import Header from '../../components/Header';
import { t, useLocale } from '../../lib/i18n';
import { getApiBaseUrl } from '../../lib/api-url';

const API_URL = getApiBaseUrl();

interface ProposalTemplate {
  id: string;
  name: string;
  template_type: string;
  created_at: string;
  updated_at: string;
  parsed?: {
    sections?: Array<{
      id: string;
      label: string;
      description: string;
      required: boolean;
      order: number;
    }>;
    scoring_items?: Array<{
      id: string;
      description: string;
      weight?: number;
    }>;
  };
}

interface ProposalProject {
  id: string;
  template_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export default function MajorProposalPage() {
  const [locale] = useLocale();
  const [activeTab, setActiveTab] = useState<'templates' | 'projects'>('templates');
  const [templates, setTemplates] = useState<ProposalTemplate[]>([]);
  const [projects, setProjects] = useState<ProposalProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    loadTemplates();
    loadProjects();
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

  const loadProjects = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/projects`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        setProjects(data);
      } else {
        throw new Error('Failed to load projects');
      }
    } catch (err: any) {
      console.error('Failed to load projects:', err);
    }
  };

  const handleUploadTemplate = async (formData: FormData) => {
    try {
      setUploading(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/templates/import`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        setShowUploadModal(false);
        await loadTemplates();
        alert(t('majorProposalTemplateCreated', { id: result.template_id }));
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to upload template');
      }
    } catch (err: any) {
      console.error('Failed to upload template:', err);
      alert(t('majorProposalUploadFailed', { error: err.message }));
    } finally {
      setUploading(false);
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
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            重大申請文件撰寫助手
          </h1>
          <p className="text-gray-600">
            上傳簡章/範本，自動萃出模板，引導你逐節撰寫申請文件
          </p>
        </div>

        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('templates')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'templates'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                模板管理
              </button>
              <button
                onClick={() => setActiveTab('projects')}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'projects'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                申請文件專案
              </button>
            </nav>
          </div>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {activeTab === 'templates' && (
          <div>
            <div className="mb-4 flex justify-between items-center">
              <h2 className="text-xl font-semibold">模板列表</h2>
              <button
                onClick={() => setShowUploadModal(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                上傳新模板
              </button>
            </div>

            {templates.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                <p className="text-gray-500 mb-4">尚無模板</p>
                <button
                  onClick={() => setShowUploadModal(true)}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  建立第一個模板
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map((template) => (
                  <Link
                    key={template.id}
                    href={`/major-proposal/templates/${template.id}`}
                    className="block p-6 bg-white rounded-lg border border-gray-200 hover:border-blue-500 hover:shadow-md transition"
                  >
                    <h3 className="text-lg font-semibold mb-2">{template.name}</h3>
                    <p className="text-sm text-gray-500 mb-2">
                      類型: {template.template_type}
                    </p>
                    {template.parsed?.sections && (
                      <p className="text-sm text-gray-600">
                        {template.parsed.sections.length} 個章節
                      </p>
                    )}
                    <p className="text-xs text-gray-400 mt-2">
                      建立於: {new Date(template.created_at).toLocaleDateString()}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'projects' && (
          <div>
            <div className="mb-4 flex justify-between items-center">
              <h2 className="text-xl font-semibold">申請文件專案</h2>
              <Link
                href="/major-proposal/projects/new"
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                建立新專案
              </Link>
            </div>

            {projects.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                <p className="text-gray-500 mb-4">尚無專案</p>
                <Link
                  href="/major-proposal/projects/new"
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  建立第一個專案
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {projects.map((project) => (
                  <Link
                    key={project.id}
                    href={`/major-proposal/projects/${project.id}`}
                    className="block p-6 bg-white rounded-lg border border-gray-200 hover:border-blue-500 hover:shadow-md transition"
                  >
                    <h3 className="text-lg font-semibold mb-2">{project.name}</h3>
                    <p className="text-sm text-gray-500 mb-2">
                      狀態: <span className="capitalize">{project.status}</span>
                    </p>
                    <p className="text-xs text-gray-400 mt-2">
                      建立於: {new Date(project.created_at).toLocaleDateString()}
                    </p>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}

        {showUploadModal && (
          <UploadTemplateModal
            onClose={() => setShowUploadModal(false)}
            onUpload={handleUploadTemplate}
            uploading={uploading}
          />
        )}
      </div>
    </div>
  );
}

interface UploadTemplateModalProps {
  onClose: () => void;
  onUpload: (formData: FormData) => Promise<void>;
  uploading: boolean;
}

function UploadTemplateModal({ onClose, onUpload, uploading }: UploadTemplateModalProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [templateType, setTemplateType] = useState('other');
  const [name, setName] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      alert(t('majorProposalSelectAtLeastOneFile' as any));
      return;
    }

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    formData.append('template_type', templateType);
    if (name) {
      formData.append('name', name);
    }

    await onUpload(formData);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full">
        <h2 className="text-xl font-semibold mb-4">上傳模板</h2>
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              檔案（PDF 或 DOCX）
            </label>
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.doc"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            {files.length > 0 && (
              <p className="mt-2 text-sm text-gray-600">
                已選擇 {files.length} 個檔案
              </p>
            )}
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              模板類型
            </label>
            <select
              value={templateType}
              onChange={(e) => setTemplateType(e.target.value)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="gov_grant">政府補助</option>
              <option value="loan">貸款申請</option>
              <option value="startup">創業提案</option>
              <option value="other">其他</option>
            </select>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              模板名稱（選填）
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('majorProposalEnterTemplateNamePlaceholder' as any)}
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded text-gray-700 hover:bg-gray-50"
              disabled={uploading}
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              disabled={uploading || files.length === 0}
            >
              {uploading ? t('majorProposalUploading' as any) : t('majorProposalUpload' as any)}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
