'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '../../../../components/Header';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ProposalTemplate {
  id: string;
  name: string;
  template_type: string;
  created_at: string;
  updated_at: string;
  parsed?: {
    title?: string;
    sections?: Array<{
      id: string;
      label: string;
      description: string;
      required: boolean;
      order: number;
      word_limit?: { min?: number; max?: number };
    }>;
    scoring_items?: Array<{
      id: string;
      description: string;
      weight?: number;
    }>;
    constraints?: {
      page_limit?: number;
      attachments?: string[];
    };
  };
}

export default function TemplateDetailPage() {
  const params = useParams();
  const router = useRouter();
  const templateId = params?.id as string;
  const [template, setTemplate] = useState<ProposalTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (templateId) {
      loadTemplate();
    }
  }, [templateId]);

  const loadTemplate = async () => {
    try {
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(`${apiUrl}/api/v1/proposal/templates/${templateId}`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.ok) {
        const data = await response.json();
        setTemplate(data);
      } else {
        throw new Error('Failed to load template');
      }
    } catch (err: any) {
      console.error('Failed to load template:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = () => {
    router.push(`/major-proposal/projects/new?template_id=${templateId}`);
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

  if (error || !template) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error || '模板不存在'}
          </div>
          <Link href="/major-proposal" className="mt-4 text-blue-600 hover:underline">
            返回模板列表
          </Link>
        </div>
      </div>
    );
  }

  const sections = template.parsed?.sections || [];
  const scoringItems = template.parsed?.scoring_items || [];

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <Link href="/major-proposal" className="text-blue-600 hover:underline mb-2 inline-block">
            ← 返回模板列表
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{template.name}</h1>
          <p className="text-gray-600">
            類型: {template.template_type} | 建立於: {new Date(template.created_at).toLocaleDateString()}
          </p>
        </div>

        <div className="mb-6">
          <button
            onClick={handleCreateProject}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            使用此模板建立新專案
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">章節結構</h2>
            {sections.length === 0 ? (
              <p className="text-gray-500">尚無章節</p>
            ) : (
              <div className="space-y-3">
                {sections
                  .sort((a, b) => a.order - b.order)
                  .map((section) => (
                    <div
                      key={section.id}
                      className="p-4 border border-gray-200 rounded hover:border-blue-500 transition"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-semibold mb-1">
                            {section.order}. {section.label}
                            {section.required && (
                              <span className="ml-2 text-xs text-red-600">必填</span>
                            )}
                          </h3>
                          <p className="text-sm text-gray-600">{section.description}</p>
                          {section.word_limit && (
                            <p className="text-xs text-gray-500 mt-1">
                              字數限制: {section.word_limit.min || 0} - {section.word_limit.max || '無上限'} 字
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">評分項目</h2>
            {scoringItems.length === 0 ? (
              <p className="text-gray-500">尚無評分項目</p>
            ) : (
              <div className="space-y-3">
                {scoringItems.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 border border-gray-200 rounded"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold mb-1">{item.id}</h3>
                        <p className="text-sm text-gray-600">{item.description}</p>
                        {item.weight !== undefined && (
                          <p className="text-xs text-gray-500 mt-1">
                            權重: {(item.weight * 100).toFixed(0)}%
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {template.parsed?.constraints && (
          <div className="mt-6 bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">格式約束</h2>
            <div className="space-y-2">
              {template.parsed.constraints.page_limit && (
                <p className="text-sm text-gray-600">
                  頁數限制: {template.parsed.constraints.page_limit} 頁
                </p>
              )}
              {template.parsed.constraints.attachments &&
                template.parsed.constraints.attachments.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-1">必附文件:</p>
                    <ul className="list-disc list-inside text-sm text-gray-600">
                      {template.parsed.constraints.attachments.map((attachment, idx) => (
                        <li key={idx}>{attachment}</li>
                      ))}
                    </ul>
                  </div>
                )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
