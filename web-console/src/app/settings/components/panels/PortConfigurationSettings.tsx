'use client';

import React, { useState, useEffect } from 'react';
import { Card } from '../Card';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';

interface PortConfig {
  backend_api: number;
  frontend: number;
  ocr_service: number;
  postgres: number;
  cloud_api?: number;
  site_hub_api?: number;
  cluster?: string;
  environment?: string;
  site?: string;
}

export function PortConfigurationSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<PortConfig>({
    backend_api: 8200,
    frontend: 8300,
    ocr_service: 8400,
    postgres: 5440,
    cloud_api: 8500,
    site_hub_api: 8102,
  });
  const [originalConfig, setOriginalConfig] = useState<PortConfig | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  // 当作用域变化时，重新加载配置并保存作用域
  useEffect(() => {
    // 只在有原始配置且作用域字段变化时重新加载
    if (originalConfig) {
      const scopeChanged =
        (originalConfig.cluster !== config.cluster) ||
        (originalConfig.environment !== config.environment) ||
        (originalConfig.site !== config.site);

      if (scopeChanged && !loading) {
        // 保存作用域到 localStorage
        if (typeof window !== 'undefined') {
          try {
            const scope = {
              cluster: config.cluster,
              environment: config.environment,
              site: config.site,
            };
            localStorage.setItem('port_config_scope', JSON.stringify(scope));

            // 同时设置到全局状态（如果存在）
            if ((window as any).__PORT_CONFIG_SCOPE__) {
              (window as any).__PORT_CONFIG_SCOPE__ = scope;
            }
          } catch (e) {
            // 忽略 localStorage 错误
          }
        }

        // 使用当前配置的作用域值重新加载
        loadConfig({
          cluster: config.cluster,
          environment: config.environment,
          site: config.site,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.cluster, config.environment, config.site]);

  const loadConfig = async (scopeOverride?: { cluster?: string; environment?: string; site?: string }) => {
    try {
      setLoading(true);
      // 读取时带上作用域参数（使用覆盖值或当前配置值）
      const params = new URLSearchParams();
      const cluster = scopeOverride?.cluster ?? config.cluster;
      const environment = scopeOverride?.environment ?? config.environment;
      const site = scopeOverride?.site ?? config.site;

      if (cluster) params.append('cluster', cluster);
      if (environment) params.append('environment', environment);
      if (site) params.append('site', site);

      // 从 localStorage 读取作用域（如果存在）
      if (typeof window !== 'undefined' && params.toString() === '') {
        try {
          const storedScope = localStorage.getItem('port_config_scope');
          if (storedScope) {
            const scope = JSON.parse(storedScope);
            if (scope.cluster) params.append('cluster', scope.cluster);
            if (scope.environment) params.append('environment', scope.environment);
            if (scope.site) params.append('site', scope.site);
          }
        } catch (e) {
          // 忽略 localStorage 错误
        }
      }

      const url = `/api/v1/system-settings/ports/${params.toString() ? '?' + params.toString() : ''}`;
      const data = await settingsApi.get<PortConfig>(url);

      // 清理数据：将 "default" 转换为 undefined（UI 显示为"全局默认"）
      const cleanedData = {
        ...data,
        environment: data.environment === 'default' ? undefined : data.environment,
        cluster: data.cluster || undefined,
        site: data.site || undefined,
      };

      setConfig(cleanedData);
      setOriginalConfig(cleanedData); // 保存原始配置用于比较

      // 保存作用域到 localStorage，供 getApiUrl 使用
      if (typeof window !== 'undefined') {
        try {
          const scope = {
            cluster: cleanedData.cluster,
            environment: cleanedData.environment,
            site: cleanedData.site,
          };
          localStorage.setItem('port_config_scope', JSON.stringify(scope));

          // 同时设置到全局状态（如果存在）
          if ((window as any).__PORT_CONFIG_SCOPE__) {
            (window as any).__PORT_CONFIG_SCOPE__ = scope;
          }
        } catch (e) {
          // 忽略 localStorage 错误
        }
      }
    } catch (error) {
      console.error('加载端口配置失败:', error);
      showNotification('error', '加载端口配置失败');
    } finally {
      setLoading(false);
    }
  };

  const validateConfig = async () => {
    try {
      setValidating(true);
      const response = await settingsApi.post<{ valid: boolean; conflicts: string[] }>(
        '/api/v1/system-settings/ports/validate',
        config
      );
      setValidationErrors(response.conflicts || []);
      return response.valid;
    } catch (error) {
      console.error('验证端口配置失败:', error);
      return false;
    } finally {
      setValidating(false);
    }
  };

  const handleChange = (key: keyof PortConfig, value: string) => {
    // 对于端口字段，验证数值范围
    if (['backend_api', 'frontend', 'ocr_service', 'postgres', 'cloud_api', 'site_hub_api'].includes(key)) {
      const numValue = parseInt(value, 10);
      if (isNaN(numValue) || numValue < 1024 || numValue > 65535) {
        return; // 无效值，不更新
      }
      setConfig(prev => ({ ...prev, [key]: numValue }));
    } else {
      // 对于作用域字段，直接更新
      setConfig(prev => ({ ...prev, [key]: value || undefined }));
    }
    // 清除验证错误
    setValidationErrors([]);
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      // 先验证配置
      const isValid = await validateConfig();
      if (!isValid) {
        showNotification('error', '端口配置存在冲突，请检查后重试');
        return;
      }

      // 检查是否修改了 PostgreSQL 端口（基于相同作用域的原值）
      const postgresChanged = originalConfig && originalConfig.postgres !== config.postgres;

      if (postgresChanged) {
        const confirmed = window.confirm(
          '警告：修改 PostgreSQL 端口需要：\n' +
          '1. 更新所有数据库连接字符串\n' +
          '2. 重启 PostgreSQL 服务\n' +
          '3. 重启所有依赖数据库的服务\n\n' +
          '是否继续？'
        );
        if (!confirmed) {
          return;
        }
      }

      // 保存配置
      const response = await settingsApi.put<{ success: boolean; message: string }>(
        '/api/v1/system-settings/ports/',
        config
      );

      showNotification('success', response.message || '端口配置已保存');

      // 保存作用域到 localStorage，供 getApiUrl 使用
      if (typeof window !== 'undefined') {
        try {
          const scope = {
            cluster: config.cluster,
            environment: config.environment,
            site: config.site,
          };
          localStorage.setItem('port_config_scope', JSON.stringify(scope));

          // 同时设置到全局状态（如果存在）
          if ((window as any).__PORT_CONFIG_SCOPE__) {
            (window as any).__PORT_CONFIG_SCOPE__ = scope;
          }
        } catch (e) {
          // 忽略 localStorage 错误
        }
      }

      // 重新加载配置以获取最新值
      await loadConfig();

      if (postgresChanged) {
        showNotification('error', '请按照提示更新数据库连接字符串并重启相关服务');
      }
    } catch (error: any) {
      console.error('保存端口配置失败:', error);
      if (error.message && error.message.includes('conflicts')) {
        const errorData = JSON.parse(error.message);
        if (errorData.conflicts) {
          setValidationErrors(errorData.conflicts);
        }
        showNotification('error', '端口配置存在冲突');
      } else {
        showNotification('error', '保存端口配置失败');
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-4">加载中...</div>
      </Card>
    );
  }

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold mb-2">端口配置</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          配置各个服务的端口号。修改后需要重启服务才能生效。
        </p>
      </div>

      {/* 验证错误提示 */}
      {validationErrors.length > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4 mb-4">
          <h4 className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
            端口配置冲突：
          </h4>
          <ul className="list-disc list-inside text-sm text-red-700 dark:text-red-300">
            {validationErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 集群/环境作用域选择 */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            集群标识 (可选)
          </label>
          <input
            type="text"
            value={config.cluster || ''}
            onChange={(e) => handleChange('cluster', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="prod-cluster-1"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">
            环境标识 (可选)
          </label>
          <select
            value={config.environment || ''}
            onChange={(e) => handleChange('environment', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="">全局默认</option>
            <option value="production">生产环境</option>
            <option value="staging">预发布环境</option>
            <option value="development">开发环境</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">
            站点标识 (可选)
          </label>
          <input
            type="text"
            value={config.site || ''}
            onChange={(e) => handleChange('site', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="site-1"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            后端 API 端口
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.backend_api}
            onChange={(e) => handleChange('backend_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8200"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            前端 Web Console 端口
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.frontend}
            onChange={(e) => handleChange('frontend', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8300"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            OCR 服务端口
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.ocr_service}
            onChange={(e) => handleChange('ocr_service', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            PostgreSQL 端口
            <span className="text-red-500 ml-1">⚠️</span>
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.postgres}
            onChange={(e) => handleChange('postgres', e.target.value)}
            className="w-full px-3 py-2 border rounded-md border-yellow-300 dark:bg-gray-700 dark:border-gray-600"
            placeholder="5440"
          />
          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
            修改此端口需要更新所有数据库连接字符串并重启服务
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Cloud API 端口 (可选)
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.cloud_api || ''}
            onChange={(e) => handleChange('cloud_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            Site-Hub API 端口 (可选)
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.site_hub_api || ''}
            onChange={(e) => handleChange('site_hub_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8102"
          />
        </div>
      </div>

      <div className="flex justify-end space-x-2 pt-4">
        <button
          onClick={validateConfig}
          disabled={validating}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50"
        >
          {validating ? '验证中...' : '验证配置'}
        </button>
        <button
          onClick={handleSave}
          disabled={saving || validationErrors.length > 0}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? '保存中...' : '保存配置'}
        </button>
      </div>
    </Card>
  );
}

