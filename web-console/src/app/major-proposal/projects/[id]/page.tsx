'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../../components/Header';
import { t } from '@/lib/i18n';

import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

interface ProposalProject {
  id: string;
  template_id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ProposalTemplate {
  id: string;
  name: string;
  parsed?: {
    sections?: Array<{
      id: string;
      label: string;
      description: string;
      required: boolean;
      order: number;
    }>;
  };
}

interface ProposalSectionDraft {
  id: string;
  project_id: string;
  template_section_id: string;
  raw_inputs: string[];
  ai_draft?: string;
  user_edited?: string;
  last_updated: string;
}

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params?.id as string;
  const [project, setProject] = useState<ProposalProject | null>(null);
  const [template, setTemplate] = useState<ProposalTemplate | null>(null);
  const [sections, setSections] = useState<Array<{
    id: string;
    label: string;
    description: string;
    required: boolean;
    order: number;
    draft?: ProposalSectionDraft;
  }>>([]);
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [assembling, setAssembling] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadProject();
      loadSections();
    }
  }, [projectId]);

  const loadProject = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/projects/${projectId}`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        setProject(data);
        await loadTemplate(data.template_id);
      } else {
        throw new Error('Failed to load project');
      }
    } catch (err: any) {
      console.error('Failed to load project:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadTemplate = async (templateId: string) => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/templates/${templateId}`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        setTemplate(data);
        const templateSections = data.parsed?.sections || [];
        setSections(templateSections.map((s: any) => ({ ...s, draft: undefined })));
        if (templateSections.length > 0 && !selectedSectionId) {
          setSelectedSectionId(templateSections[0].id);
        }
      }
    } catch (err: any) {
      console.error('Failed to load template:', err);
    }
  };

  const loadSections = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/projects/${projectId}/sections`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const drafts = await response.json();
        setSections((prev) =>
          prev.map((section) => {
            const draft = drafts.find((d: ProposalSectionDraft) => d.template_section_id === section.id);
            return { ...section, draft };
          })
        );
      }
    } catch (err: any) {
      console.error('Failed to load sections:', err);
    }
  };

  const handleGenerateSection = async (sectionId: string, rawInputs: string[]) => {
    try {
      setGenerating(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/proposal/projects/${projectId}/sections/${sectionId}/generate`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            raw_inputs: rawInputs,
            target_language: 'zh-TW',
          }),
        }
      );

      if (response.ok) {
        await loadSections();
        alert(t('majorProposalDraftGenerated'));
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate section');
      }
    } catch (err: any) {
      console.error('Failed to generate section:', err);
      alert(t('majorProposalGenerateFailed', { error: err.message }));
    } finally {
      setGenerating(false);
    }
  };

  const handleAssemble = async () => {
    try {
      setAssembling(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/projects/${projectId}/assemble`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const result = await response.json();
        alert(t('majorProposalAssembled', { path: result.proposal_docx_path }));
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to assemble proposal');
      }
    } catch (err: any) {
      console.error('Failed to assemble proposal:', err);
      alert(t('majorProposalAssembleFailed', { error: err.message }));
    } finally {
      setAssembling(false);
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

  if (error || !project) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error || t('majorProposalProjectNotFound')}
          </div>
          <Link href="/major-proposal" className="mt-4 text-blue-600 hover:underline">
            返回專案列表
          </Link>
        </div>
      </div>
    );
  }

  const selectedSection = sections.find((s) => s.id === selectedSectionId);
  const allRequiredSectionsHaveDrafts = sections
    .filter((s) => s.required)
    .every((s) => s.draft?.ai_draft || s.draft?.user_edited);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/major-proposal" className="text-blue-600 hover:underline mb-2 inline-block">
            ← 返回專案列表
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{project.name}</h1>
          <p className="text-gray-600">
            狀態: <span className="capitalize">{project.status}</span> | 建立於:{' '}
            {new Date(project.created_at).toLocaleDateString()}
          </p>
        </div>

        <div className="mb-4 flex justify-end">
          <button
            onClick={handleAssemble}
            disabled={!allRequiredSectionsHaveDrafts || assembling}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {assembling ? t('majorProposalAssembling') : t('majorProposalAssembleComplete')}
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <h2 className="text-lg font-semibold mb-4">章節列表</h2>
              <div className="space-y-2">
                {sections
                  .sort((a, b) => a.order - b.order)
                  .map((section) => {
                    const hasDraft = section.draft?.ai_draft || section.draft?.user_edited;
                    return (
                      <button
                        key={section.id}
                        onClick={() => setSelectedSectionId(section.id)}
                        className={`w-full text-left p-3 rounded border transition ${
                          selectedSectionId === section.id
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium">
                                {section.order}. {section.label}
                              </span>
                              {section.required && (
                                <span className="text-xs text-red-600">必填</span>
                              )}
                              {hasDraft && (
                                <span className="text-xs text-green-600">✓</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            {selectedSection ? (
              <SectionWritingPanel
                section={selectedSection}
                onGenerate={handleGenerateSection}
                generating={generating}
                projectId={projectId}
              />
            ) : (
              <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-500">
                請選擇一個章節開始撰寫
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface SectionWritingPanelProps {
  section: {
    id: string;
    label: string;
    description: string;
    required: boolean;
    order: number;
    draft?: ProposalSectionDraft;
  };
  onGenerate: (sectionId: string, rawInputs: string[]) => Promise<void>;
  generating: boolean;
  projectId: string;
}

function SectionWritingPanel({ section, onGenerate, generating, projectId }: SectionWritingPanelProps) {
  const [rawInputs, setRawInputs] = useState<string[]>(['']);
  const [editingContent, setEditingContent] = useState<string>('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (section.draft) {
      setRawInputs(section.draft.raw_inputs.length > 0 ? section.draft.raw_inputs : ['']);
      setEditingContent(section.draft.user_edited || section.draft.ai_draft || '');
    } else {
      setRawInputs(['']);
      setEditingContent('');
    }
  }, [section.draft]);

  const handleAddInput = () => {
    setRawInputs([...rawInputs, '']);
  };

  const handleInputChange = (index: number, value: string) => {
    const newInputs = [...rawInputs];
    newInputs[index] = value;
    setRawInputs(newInputs);
  };

  const handleRemoveInput = (index: number) => {
    if (rawInputs.length > 1) {
      setRawInputs(rawInputs.filter((_, i) => i !== index));
    }
  };

  const handleGenerate = async () => {
    const nonEmptyInputs = rawInputs.filter((input) => input.trim());
    if (nonEmptyInputs.length === 0) {
      alert(t('majorProposalEnterContent'));
      return;
    }
    await onGenerate(section.id, nonEmptyInputs);
  };

  const handleSaveEdit = async () => {
    if (!section.draft?.id) return;

    try {
      setSaving(true);
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/proposal/projects/${projectId}/sections/${section.draft.id}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_edited: editingContent,
          }),
        }
      );

      if (response.ok) {
        alert(t('majorProposalSaved'));
      } else {
        throw new Error('Failed to save');
      }
    } catch (err: any) {
      console.error('Failed to save:', err);
      alert(t('majorProposalSaveFailed', { error: err.message }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h2 className="text-xl font-semibold mb-2">
        {section.order}. {section.label}
        {section.required && <span className="ml-2 text-sm text-red-600">必填</span>}
      </h2>
      <p className="text-sm text-gray-600 mb-6">{section.description}</p>

      {!section.draft?.ai_draft && !section.draft?.user_edited ? (
        <div>
          <h3 className="font-medium mb-3">請提供以下資訊：</h3>
          <div className="space-y-3 mb-4">
            {rawInputs.map((input, index) => (
              <div key={index} className="flex gap-2">
                <textarea
                  value={input}
                  onChange={(e) => handleInputChange(index, e.target.value)}
                  placeholder={t('majorProposalEnterInfo')}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  rows={3}
                />
                {rawInputs.length > 1 && (
                  <button
                    onClick={() => handleRemoveInput(index)}
                    className="px-3 py-2 text-red-600 hover:bg-red-50 rounded"
                  >
                    刪除
                  </button>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={handleAddInput}
            className="mb-4 px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded"
          >
            + 新增輸入欄位
          </button>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {generating ? t('majorProposalGenerating') : t('majorProposalGenerateDraft')}
          </button>
        </div>
      ) : (
        <div>
          <h3 className="font-medium mb-3">章節內容：</h3>
          <textarea
            value={editingContent}
            onChange={(e) => setEditingContent(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 mb-4"
            rows={15}
          />
          <div className="flex justify-end space-x-3">
            <button
              onClick={handleSaveEdit}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? t('majorProposalSaving') : t('majorProposalSaveEdit')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
