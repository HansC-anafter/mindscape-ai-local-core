'use client';

import React, { useState, useEffect } from 'react';

interface WordPressSite {
  site_id: string;
  site_name: string;
  site_url: string;
  configured_at?: string;
  status?: string;
  last_tested_at?: string;
}

interface WordPressSitesPanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function WordPressSitesPanel({
  workspaceId,
  apiUrl
}: WordPressSitesPanelProps) {
  const [sites, setSites] = useState<WordPressSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [testingSiteId, setTestingSiteId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ site_id: string; success: boolean; message: string } | null>(null);

  const [form, setForm] = useState({
    site_id: '',
    site_name: '',
    site_url: '',
    site_api_key: ''
  });

  useEffect(() => {
    loadSites();
  }, [workspaceId]);

  const loadSites = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/wordpress/sites`
      );
      if (!response.ok) {
        throw new Error('Failed to load WordPress sites');
      }
      const data = await response.json();
      setSites(data.sites || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sites');
    } finally {
      setLoading(false);
    }
  };

  const handleAddSite = async () => {
    if (!form.site_id || !form.site_name || !form.site_url || !form.site_api_key) {
      setError('Please fill in all fields');
      return;
    }

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/wordpress/sites`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form)
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to add site' }));
        throw new Error(errorData.detail || 'Failed to add site');
      }

      setShowAddForm(false);
      setForm({ site_id: '', site_name: '', site_url: '', site_api_key: '' });
      await loadSites();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add site');
    }
  };

  const handleTestConnection = async (siteId: string) => {
    setTestingSiteId(siteId);
    setTestResult(null);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/wordpress/sites/${siteId}/test`,
        {
          method: 'POST'
        }
      );

      const data = await response.json();
      setTestResult({
        site_id: siteId,
        success: data.success || false,
        message: data.message || 'Connection test completed'
      });

      if (data.success) {
        await loadSites();
      }
    } catch (err) {
      setTestResult({
        site_id: siteId,
        success: false,
        message: err instanceof Error ? err.message : 'Connection test failed'
      });
    } finally {
      setTestingSiteId(null);
    }
  };

  const handleDeleteSite = async (siteId: string) => {
    if (!confirm(`Are you sure you want to delete site ${siteId}?`)) {
      return;
    }

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/wordpress/sites/${siteId}`,
        {
          method: 'DELETE'
        }
      );

      if (!response.ok) {
        throw new Error('Failed to delete site');
      }

      await loadSites();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete site');
    }
  };

  if (loading) {
    return (
      <div className="p-4">
        <div className="text-gray-500 dark:text-gray-400">載入中...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          WordPress 站點配置
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          管理此 workspace 的 WordPress 站點連接配置
        </p>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {testResult && (
        <div
          className={`border rounded-lg p-3 ${
            testResult.success
              ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
          }`}
        >
          <p
            className={`text-sm ${
              testResult.success
                ? 'text-green-700 dark:text-green-300'
                : 'text-red-700 dark:text-red-300'
            }`}
          >
            {testResult.message}
          </p>
        </div>
      )}

      {!showAddForm ? (
        <button
          onClick={() => setShowAddForm(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          + 添加站點
        </button>
      ) : (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3">
          <h4 className="font-medium text-gray-900 dark:text-gray-100">添加新站點</h4>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Site ID
            </label>
            <input
              type="text"
              value={form.site_id}
              onChange={(e) => setForm({ ...form, site_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md"
              placeholder="site_e2a7af26c0d2489c"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              站點名稱
            </label>
            <input
              type="text"
              value={form.site_name}
              onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md"
              placeholder="yogacookie"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              WordPress URL
            </label>
            <input
              type="url"
              value={form.site_url}
              onChange={(e) => setForm({ ...form, site_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md"
              placeholder="https://yogacookie.app"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              API Key
            </label>
            <input
              type="password"
              value={form.site_api_key}
              onChange={(e) => setForm({ ...form, site_api_key: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md"
              placeholder="your_api_key"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddSite}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              保存
            </button>
            <button
              onClick={() => {
                setShowAddForm(false);
                setForm({ site_id: '', site_name: '', site_url: '', site_api_key: '' });
              }}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {sites.length === 0 ? (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
          尚未配置任何 WordPress 站點
        </div>
      ) : (
        <div className="space-y-3">
          {sites.map((site) => (
            <div
              key={site.site_id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                      {site.site_name}
                    </h4>
                    <span
                      className={`px-2 py-1 text-xs rounded ${
                        site.status === 'active'
                          ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                          : site.status === 'error'
                          ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                          : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      {site.status || 'unknown'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                    {site.site_url}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-500">
                    Site ID: {site.site_id}
                  </p>
                  {site.configured_at && (
                    <p className="text-xs text-gray-500 dark:text-gray-500">
                      配置時間: {new Date(site.configured_at).toLocaleString('zh-TW')}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTestConnection(site.site_id)}
                    disabled={testingSiteId === site.site_id}
                    className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
                  >
                    {testingSiteId === site.site_id ? '測試中...' : '測試連接'}
                  </button>
                  <button
                    onClick={() => handleDeleteSite(site.site_id)}
                    className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                  >
                    刪除
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
