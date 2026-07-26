'use client';

import React, { useState } from 'react';
import { useT } from '../../../../lib/i18n';
import { showNotification } from '../../hooks/useSettingsNotification';
import { settingsApi } from '../../utils/settingsApi';
import { ModelConfigCardView } from './modelConfigCard/ModelConfigCardView';
import {
  getDefaultMaxTokens,
  getLocalRuntimeMaxTokensCap,
  MAX_OUTPUT_TOKEN_SLIDER_MAX,
  resolveInitialMaxOutputTokens,
} from './modelConfigCard/tokenLimits';
import type { ModelConfigCardProps } from './modelConfigCard/types';

export type { PullState } from './modelConfigCard/types';

export function ModelConfigCard({
  card,
  onConfigSaved,
  pullState,
  onPullModel,
  onCancelPull,
  onRemoveModel,
}: ModelConfigCardProps) {
  const t = useT();
  const { model, base_url, project_id, location, provider_config, quota_info } = card;
  const [showModelOverride, setShowModelOverride] = useState(false);

  const providerApiKey = provider_config?.api_key || '';
  const providerBaseUrl = provider_config?.base_url || base_url || '';
  const providerProjectId = provider_config?.project_id || project_id || '';
  const providerLocation = provider_config?.location || location || 'us-central1';

  const [apiKey, setApiKey] = useState(providerApiKey);
  const [baseUrl, setBaseUrl] = useState(providerBaseUrl);
  const [projectId, setProjectId] = useState(providerProjectId);
  const [vertexLocation, setVertexLocation] = useState(providerLocation);

  const [modelApiKey, setModelApiKey] = useState('');
  const [modelBaseUrl, setModelBaseUrl] = useState('');
  const [modelProjectId, setModelProjectId] = useState('');
  const [modelLocation, setModelLocation] = useState('');

  const defaultMaxTokens = getDefaultMaxTokens(model);
  const initialRuntimeEngine = model.metadata?.runtime_engine || 'auto';
  const initialMaxOutputTokens = resolveInitialMaxOutputTokens(
    model,
    defaultMaxTokens,
    initialRuntimeEngine
  );

  const [maxOutputTokens, setMaxOutputTokens] = useState<number>(
    initialMaxOutputTokens
  );

  const [runtimeEngine, setRuntimeEngine] = useState<string>(
    initialRuntimeEngine
  );

  const localRuntimeMaxTokensCap = getLocalRuntimeMaxTokensCap(model, runtimeEngine);
  const maxOutputTokenSliderMax = localRuntimeMaxTokensCap ?? MAX_OUTPUT_TOKEN_SLIDER_MAX;
  const effectiveMaxOutputTokens = Math.min(maxOutputTokens, maxOutputTokenSliderMax);

  const [temperature, setTemperature] = useState<number>(
    model.metadata?.temperature ?? 0.6
  );

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [jsonFileName, setJsonFileName] = useState<string>('');

  const pulling = pullState != null && (pullState.status === 'starting' || pullState.status === 'downloading');
  const pullProgress = pullState?.progress ?? 0;
  const pullStatus = pullState?.status ?? '';
  const pullMessage = pullState?.message ?? '';
  const pullTotalBytes = pullState?.totalBytes ?? 0;
  const pullDownloadedBytes = pullState?.downloadedBytes ?? 0;

  React.useEffect(() => {
    setApiKey(providerApiKey);
    setBaseUrl(providerBaseUrl);
    setProjectId(providerProjectId);
    setVertexLocation(providerLocation);
  }, [providerApiKey, providerBaseUrl, providerProjectId, providerLocation]);

  const handleJsonFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/json' && !file.name.endsWith('.json')) {
      setTestResult({ success: false, message: 'Please select a valid JSON file' as any });
      return;
    }

    setJsonFile(file);
    setJsonFileName(file.name);

    try {
      const text = await file.text();
      const jsonData = JSON.parse(text);

      if (jsonData.type !== 'service_account') {
        setTestResult({ success: false, message: 'Invalid service account JSON file' as any });
        return;
      }

      if (jsonData.project_id) {
        setProjectId(jsonData.project_id);
      }
      if (jsonData.private_key && jsonData.client_email) {
        const credentialsJson = JSON.stringify({
          type: jsonData.type,
          project_id: jsonData.project_id,
          private_key_id: jsonData.private_key_id,
          private_key: jsonData.private_key,
          client_email: jsonData.client_email,
          client_id: jsonData.client_id,
          auth_uri: jsonData.auth_uri,
          token_uri: jsonData.token_uri,
          auth_provider_x509_cert_url: jsonData.auth_provider_x509_cert_url,
          client_x509_cert_url: jsonData.client_x509_cert_url,
        });
        setApiKey(credentialsJson);
      }
    } catch (err) {
      setTestResult({ success: false, message: `Failed to parse JSON file: ${err instanceof Error ? err.message : 'Unknown error'}` });
    }
  };

  const buildModelMetadataUpdates = (): Record<string, any> => {
    const updates: Record<string, any> = {};
    if (model.metadata?.max_output_tokens !== effectiveMaxOutputTokens) {
      updates.max_output_tokens = effectiveMaxOutputTokens;
    }
    if (runtimeEngine !== (model.metadata?.runtime_engine || 'auto')) {
      updates.runtime_engine = runtimeEngine;
    }
    if (temperature !== (model.metadata?.temperature ?? 0.6)) {
      updates.temperature = temperature;
    }
    return updates;
  };

  const persistModelMetadataUpdates = async (): Promise<boolean> => {
    const updates = buildModelMetadataUpdates();
    if (Object.keys(updates).length === 0) {
      return false;
    }

    await settingsApi.patch<{ success: boolean }>(
      `/api/v1/system-settings/models/${model.id}/metadata`,
      updates
    );
    return true;
  };

  const handleSaveProviderConfig = async () => {
    try {
      setSaving(true);
      await persistModelMetadataUpdates();
      const config: any = {
        provider_level: true
      };

      if (apiKey) {
        config.api_key = apiKey;
      }

      if (model.provider === 'ollama' && baseUrl) {
        config.base_url = baseUrl;
      }

      if (model.provider === 'vertex-ai') {
        if (projectId) {
          config.project_id = projectId;
        }
        if (vertexLocation) {
          config.location = vertexLocation;
        }
        if (apiKey) {
          config.api_key = apiKey;
        }
      }

      const response = await settingsApi.put<{ success: boolean; message: string }>(`/api/v1/system-settings/models/${model.id}/config`, config);
      const message = response?.message || t('configSaved' as any) || 'Settings saved successfully';
      showNotification('success', message);
      setJsonFile(null);
      setJsonFileName('');
      if (onConfigSaved) {
        onConfigSaved();
      }
    } catch (err) {
      console.error('Failed to save provider configuration:', err);
      showNotification('error', `Failed to save: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveModelOverride = async () => {
    try {
      setSaving(true);
      await persistModelMetadataUpdates();

      const config: any = {
        provider_level: false
      };

      if (modelApiKey) config.api_key = modelApiKey;
      if (model.provider === 'ollama' && modelBaseUrl) config.base_url = modelBaseUrl;

      if (model.provider === 'vertex-ai') {
        if (modelProjectId) config.project_id = modelProjectId;
        if (modelLocation) config.location = modelLocation;
      }

      const response = await settingsApi.put<{ success: boolean; message: string }>(`/api/v1/system-settings/models/${model.id}/config`, config);
      const message = response?.message || t('configSaved' as any) || 'Settings saved successfully';

      setModelApiKey('');
      setModelBaseUrl('');
      setModelProjectId('');
      setModelLocation('');
      showNotification('success', message);

      if (onConfigSaved) {
        onConfigSaved();
      }
    } catch (err) {
      console.error('Failed to save model override:', err);
      showNotification('error', `Failed to save: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const result = await settingsApi.post<{ success: boolean; message: string }>(
        `/api/v1/system-settings/models/${model.id}/test`,
        {}
      );
      if (result.success) {
        setTestResult({ success: true, message: result.message });
      } else {
        setTestResult({ success: false, message: `${t('testFailedWithError' as any)}: ${result.message}` });
      }
    } catch (err) {
      setTestResult({ success: false, message: `${t('testFailedWithError' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}` });
    } finally {
      setTesting(false);
    }
  };

  const handlePullModel = async () => {
    if (onPullModel) {
      onPullModel(model);
    }
  };

  const handleRemoveModel = () => {
    if (onRemoveModel && confirm(`Remove "${model.display_name}"?`)) {
      onRemoveModel(model.id);
    }
  };

  return (
    <ModelConfigCardView
      model={model}
      providerConfig={provider_config}
      apiKey={apiKey}
      baseUrl={baseUrl}
      projectId={projectId}
      vertexLocation={vertexLocation}
      jsonFileName={jsonFileName}
      saving={saving}
      onApiKeyChange={setApiKey}
      onBaseUrlChange={setBaseUrl}
      onProjectIdChange={setProjectId}
      onVertexLocationChange={setVertexLocation}
      onJsonFileChange={handleJsonFileChange}
      onSaveProviderConfig={handleSaveProviderConfig}
      pullStatus={pullStatus}
      onRemoveModel={onRemoveModel ? handleRemoveModel : undefined}
      showModelOverride={showModelOverride}
      modelApiKey={modelApiKey}
      modelBaseUrl={modelBaseUrl}
      modelProjectId={modelProjectId}
      modelLocation={modelLocation}
      runtimeEngine={runtimeEngine}
      temperature={temperature}
      maxOutputTokenSliderMax={maxOutputTokenSliderMax}
      effectiveMaxOutputTokens={effectiveMaxOutputTokens}
      defaultMaxTokens={defaultMaxTokens}
      localRuntimeMaxTokensCap={localRuntimeMaxTokensCap}
      onToggleShowModelOverride={() => setShowModelOverride(!showModelOverride)}
      onSaveModelOverride={handleSaveModelOverride}
      onModelApiKeyChange={setModelApiKey}
      onModelBaseUrlChange={setModelBaseUrl}
      onModelProjectIdChange={setModelProjectId}
      onModelLocationChange={setModelLocation}
      onRuntimeEngineChange={setRuntimeEngine}
      onTemperatureChange={setTemperature}
      onMaxOutputTokensChange={setMaxOutputTokens}
      testing={testing}
      pulling={pulling}
      pullProgress={pullProgress}
      pullMessage={pullMessage}
      pullTotalBytes={pullTotalBytes}
      pullDownloadedBytes={pullDownloadedBytes}
      pullState={pullState}
      testResult={testResult}
      onTestConnection={handleTestConnection}
      onPullModel={handlePullModel}
      onCancelPull={onCancelPull}
      quotaInfo={quota_info}
    />
  );
}
