'use client';

import React, { useEffect, useState } from 'react';
import { Card } from './Card';
import { HuggingFaceCredentialsSettings } from './HuggingFaceCredentialsSettings';
import { GoogleOAuthSettings } from './GoogleOAuthSettings';
import { settingsApi } from '../utils/settingsApi';

interface CredentialsAndOAuthPanelProps {
  activeSection?: string;
  activeProvider?: string;
  onNavigate: (section: string, provider?: string) => void;
}

interface HuggingFaceSummary {
  api_key_configured: boolean;
}

interface GoogleOAuthSummary {
  is_configured: boolean;
  client_id?: string;
}

function ProviderCard({
  title,
  kind,
  description,
  statusLabel,
  statusTone,
  actionLabel,
  onOpen,
}: {
  title: string;
  kind: string;
  description: string;
  statusLabel: string;
  statusTone: 'ready' | 'pending';
  actionLabel: string;
  onOpen: () => void;
}) {
  const statusClass =
    statusTone === 'ready'
      ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300'
      : 'border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300';

  return (
    <div className="rounded-xl border border-default dark:border-gray-700 bg-surface dark:bg-gray-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-base font-semibold text-primary dark:text-gray-100">{title}</div>
          <div className="mt-1 text-xs uppercase tracking-wide text-secondary dark:text-gray-400">{kind}</div>
        </div>
        <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium ${statusClass}`}>
          {statusLabel}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-secondary dark:text-gray-400">{description}</p>
      <div className="mt-4">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center rounded-md border border-default dark:border-gray-600 px-4 py-2 text-sm font-medium text-primary dark:text-gray-100 hover:bg-surface-accent dark:hover:bg-gray-800"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

export function CredentialsAndOAuthPanel({
  activeSection,
  activeProvider,
  onNavigate,
}: CredentialsAndOAuthPanelProps) {
  const section = activeSection || 'service-credentials';
  const normalizedSection = section === 'oauth' ? 'oauth-integrations' : section;
  const [hfSummary, setHfSummary] = useState<HuggingFaceSummary | null>(null);
  const [googleSummary, setGoogleSummary] = useState<GoogleOAuthSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  useEffect(() => {
    if (activeProvider) {
      return;
    }

    let cancelled = false;
    const loadSummary = async () => {
      try {
        setLoadingSummary(true);
        if (normalizedSection === 'service-credentials') {
          const data = await settingsApi.get<HuggingFaceSummary>('/api/v1/system-settings/huggingface-auth');
          if (!cancelled) {
            setHfSummary(data);
          }
          return;
        }
        if (normalizedSection === 'oauth-integrations') {
          const data = await settingsApi.get<GoogleOAuthSummary>('/api/v1/system-settings/google-oauth');
          if (!cancelled) {
            setGoogleSummary(data);
          }
        }
      } catch {
        if (!cancelled) {
          if (normalizedSection === 'service-credentials') {
            setHfSummary(null);
          }
          if (normalizedSection === 'oauth-integrations') {
            setGoogleSummary(null);
          }
        }
      } finally {
        if (!cancelled) {
          setLoadingSummary(false);
        }
      }
    };

    void loadSummary();
    return () => {
      cancelled = true;
    };
  }, [activeProvider, normalizedSection]);

  if (normalizedSection === 'service-credentials' && activeProvider === 'huggingface') {
    return (
      <Card>
        <div className="space-y-6">
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => onNavigate('service-credentials')}
              className="inline-flex items-center gap-2 rounded-md border border-default dark:border-gray-600 px-4 py-2 text-sm font-medium text-secondary dark:text-gray-300 hover:bg-surface-accent dark:hover:bg-gray-800 hover:text-primary dark:hover:text-gray-100"
            >
              <span aria-hidden="true">←</span>
              <span>返回服務憑證總覽</span>
            </button>
            <div>
              <h2 className="text-lg font-semibold text-primary dark:text-gray-100">服務憑證</h2>
              <p className="mt-1 text-sm text-secondary dark:text-gray-400">
                管理需要 access token 或 API key 的外部服務憑證。
              </p>
            </div>
          </div>
          <HuggingFaceCredentialsSettings />
        </div>
      </Card>
    );
  }

  if (normalizedSection === 'oauth-integrations' && activeProvider === 'google') {
    return (
      <Card>
        <div className="space-y-6">
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => onNavigate('oauth-integrations')}
              className="inline-flex items-center gap-2 rounded-md border border-default dark:border-gray-600 px-4 py-2 text-sm font-medium text-secondary dark:text-gray-300 hover:bg-surface-accent dark:hover:bg-gray-800 hover:text-primary dark:hover:text-gray-100"
            >
              <span aria-hidden="true">←</span>
              <span>返回 OAuth 整合總覽</span>
            </button>
            <div>
              <h2 className="text-lg font-semibold text-primary dark:text-gray-100">OAuth 整合</h2>
              <p className="mt-1 text-sm text-secondary dark:text-gray-400">
                管理需要瀏覽器授權流程的外部整合。
              </p>
            </div>
          </div>
          <GoogleOAuthSettings />
        </div>
      </Card>
    );
  }

  if (normalizedSection === 'oauth-integrations') {
    return (
      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-primary dark:text-gray-100">OAuth 整合</h2>
            <p className="mt-1 text-sm text-secondary dark:text-gray-400">
              這裡集中管理需要瀏覽器授權與 redirect callback 的整合服務。
            </p>
          </div>

          {loadingSummary ? (
            <div className="text-sm text-secondary dark:text-gray-400">載入中...</div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              <ProviderCard
                title="Google"
                kind="OAuth Integration"
                description="提供 Google Drive 與相關 Google 工具整合所需的 OAuth Client 設定。"
                statusLabel={googleSummary?.is_configured ? '已設定' : '未設定'}
                statusTone={googleSummary?.is_configured ? 'ready' : 'pending'}
                actionLabel={googleSummary?.is_configured ? '查看設定' : '前往設定'}
                onOpen={() => onNavigate('oauth-integrations', 'google')}
              />
            </div>
          )}
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-primary dark:text-gray-100">服務憑證</h2>
          <p className="mt-1 text-sm text-secondary dark:text-gray-400">
            這裡集中管理以 access token、API key 或 PAT 形式提供的外部服務憑證。
          </p>
        </div>

        {loadingSummary ? (
          <div className="text-sm text-secondary dark:text-gray-400">載入中...</div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <ProviderCard
              title="Hugging Face"
              kind="Access Token"
              description="供 Hugging Face 模型下載、LAF 權重同步，以及需要授權的模型資產拉取共用。"
              statusLabel={hfSummary?.api_key_configured ? '已設定' : '未設定'}
              statusTone={hfSummary?.api_key_configured ? 'ready' : 'pending'}
              actionLabel={hfSummary?.api_key_configured ? '查看設定' : '前往設定'}
              onOpen={() => onNavigate('service-credentials', 'huggingface')}
            />
          </div>
        )}
      </div>
    </Card>
  );
}
