'use client';

import React, { useState, useEffect } from 'react';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { Card } from '../settings/components/Card';

interface PublishAdapter {
  id: string;
  name: string;
  description: string;
  type: 'cloud' | 'self-hosted' | 'hybrid';
  enabled: boolean;
  configured: boolean;
  config?: Record<string, any>;
}

export default function CloudPublishPage() {
  const [loading, setLoading] = useState(true);
  const [adapters, setAdapters] = useState<PublishAdapter[]>([]);
  const [selectedAdapter, setSelectedAdapter] = useState<PublishAdapter | null>(null);

  useEffect(() => {
    loadAdapters();
  }, []);

  const loadAdapters = async () => {
    try {
      setLoading(true);
      // TODO: 從 API 載入 adapters
      // const response = await fetch('/api/v1/publish-adapters');
      // if (response.ok) {
      //   const data = await response.json();
      //   setAdapters(data);
      // }
      setAdapters([]);
    } catch (error) {
      console.error('載入發佈適配器失敗:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigureAdapter = (adapter: PublishAdapter) => {
    setSelectedAdapter(adapter);
    // TODO: 打開配置對話框
  };

  const handlePublish = async (adapterId: string) => {
    // TODO: 實現發佈邏輯
    console.log('發佈到:', adapterId);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-900">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            {t('loading' as any)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-900">
      <Header />

      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            雲端發佈
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            將 Playbook 和 Capability 發佈到雲端服務或自託管平台。透過 Adapter 機制整合不同的發佈目標。
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Adapters List */}
          <Card>
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                  發佈適配器
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  選擇或配置發佈目標適配器
                </p>
              </div>

              <div className="space-y-3">
                {adapters.length === 0 ? (
                  <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                    尚無可用的發佈適配器
                  </div>
                ) : (
                  adapters.map((adapter) => (
                    <div
                      key={adapter.id}
                      className={`border rounded-lg p-4 space-y-3 ${
                        adapter.enabled
                          ? 'border-gray-200 dark:border-gray-700'
                          : 'border-gray-300 dark:border-gray-600 opacity-60'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-gray-900 dark:text-gray-100">
                              {adapter.name}
                            </h3>
                            <span className={`px-2 py-1 text-xs rounded ${
                              adapter.enabled
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                                : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                            }`}>
                              {adapter.enabled ? '已啟用' : '已停用'}
                            </span>
                            <span className={`px-2 py-1 text-xs rounded ${
                              adapter.configured
                                ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/20 dark:text-orange-400'
                                : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
                            }`}>
                              {adapter.configured ? '已配置' : '未配置'}
                            </span>
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            {adapter.description}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                            類型: {adapter.type === 'cloud' ? '雲端' : adapter.type === 'self-hosted' ? '自託管' : '混合'}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleConfigureAdapter(adapter)}
                          className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                        >
                          {adapter.configured ? '編輯配置' : '配置'}
                        </button>
                        {adapter.configured && adapter.enabled && (
                          <button
                            type="button"
                            onClick={() => handlePublish(adapter.id)}
                            className="px-3 py-1.5 text-sm bg-orange-600 text-white rounded hover:bg-orange-700"
                          >
                            發佈
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </Card>

          {/* Publish Content */}
          <Card>
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                  發佈內容
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  選擇要發佈的 Playbook 或 Capability
                </p>
              </div>

              <div className="space-y-3">
                <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                  發佈內容選擇功能開發中...
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Adapter Mechanism Info */}
        <Card className="mt-6">
          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                關於 Adapter 機制
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Adapter 機制允許您整合不同的發佈目標，每個 Adapter 負責處理特定平台的發佈邏輯。
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 space-y-2">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                Adapter 類型：
              </h3>
              <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
                <li><strong>雲端</strong>：發佈到雲端服務提供商</li>
                <li><strong>自託管</strong>：發佈到自託管的服務</li>
                <li><strong>混合</strong>：支援雲端和自託管的混合模式</li>
              </ul>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

