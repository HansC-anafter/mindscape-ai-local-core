'use client';

import React, { useMemo } from 'react';

export interface StoryboardScenePatchPayload {
  source_scene_id?: string;
  object_assets?: Array<Record<string, any>>;
  object_reuse_plan?: {
    usage_bindings?: Array<Record<string, any>>;
    usage_scene_ids?: string[];
    [key: string]: any;
  } | null;
  object_workload_snapshot?: Record<string, any> | null;
  [key: string]: any;
}

export interface ScenePatchSummary {
  sourceSceneId: string;
  objectAssetCount: number;
  usageBindingCount: number;
  impactRegionMode?: string;
  qualityGateState?: string;
  affectedObjectCount?: number;
  impactRegionBBoxLabel?: string;
}

export interface ScenePatchStatusMessage {
  tone: 'success' | 'error' | 'info';
  message: string;
}

export function buildPdScenePatchSuccessText(params: {
  sceneId?: string | null;
  artifactId?: string | null;
}) {
  return [
    'PD Storyboard 已回寫',
    `目標場景：${params.sceneId || '-'}`,
    `artifact：${params.artifactId || '-'}`,
  ].join('\n');
}

export function buildMmsScenePatchSuccessText(params: {
  sceneId?: string | null;
}) {
  return [
    'MMS Storyboard 已更新',
    `目標場景：${params.sceneId || '-'}`,
  ].join('\n');
}

export function buildScenePatchFailureText(scope: 'PD' | 'MMS', error: unknown) {
  const detail = error instanceof Error ? error.message : String(error);
  return `${scope} storyboard 套用失敗：${detail}`;
}

interface PdActionConfig {
  sessionId: string;
  onSessionIdChange: (value: string) => void;
  sessionIdReadOnly?: boolean;
  sessionIdPlaceholder?: string;
  artifactId?: string;
  onArtifactIdChange?: (value: string) => void;
  artifactPlaceholder?: string;
  hideArtifactId?: boolean;
  applying: boolean;
  result?: ScenePatchStatusMessage | null;
  onApply: () => void | Promise<void>;
  buttonLabel?: string;
  description?: string;
}

interface MmsActionConfig {
  storyboardJson: string;
  onStoryboardJsonChange: (value: string) => void;
  onResetStoryboard?: () => void;
  applying: boolean;
  result?: ScenePatchStatusMessage | null;
  onApply: () => void | Promise<void>;
  buttonLabel?: string;
  description?: string;
}

interface ScenePatchConsoleProps {
  theme?: 'light' | 'dark';
  title?: string;
  description: string;
  patchMode: 'editable' | 'derived';
  patch?: StoryboardScenePatchPayload | null;
  patchJson?: string;
  onPatchJsonChange?: (value: string) => void;
  patchError?: string | null;
  summary?: ScenePatchSummary | null;
  sceneId: string;
  onSceneIdChange: (value: string) => void;
  sceneIdPlaceholder?: string;
  onClearPatch?: () => void;
  pdAction?: PdActionConfig;
  mmsAction?: MmsActionConfig;
}

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

function panelClasses(theme: 'light' | 'dark') {
  if (theme === 'dark') {
    return {
      shell: 'space-y-4',
      surface: 'rounded-2xl border border-gray-700 bg-gray-800/70 p-4',
      muted: 'text-xs text-gray-400',
      text: 'text-sm text-white',
      label: 'mb-1 block text-xs font-medium text-gray-300',
      input: 'w-full rounded-lg border border-gray-600 bg-gray-950 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-gray-500 focus:border-blue-400',
      textarea: 'w-full rounded-xl border border-gray-600 bg-gray-950 px-3 py-3 font-mono text-xs leading-6 text-white outline-none transition-colors placeholder:text-gray-500 focus:border-blue-400',
      chip: 'rounded-full border border-gray-700 bg-gray-800 px-2.5 py-1 text-[11px] text-gray-300',
      chipEmpty: 'rounded-full border border-dashed border-gray-700 px-2.5 py-1 text-[11px] text-gray-400',
      subtleButton: 'rounded-lg border border-gray-600 px-3 py-1.5 text-xs text-gray-200 transition-colors hover:border-gray-500 hover:bg-gray-800',
      primaryButton: 'rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-60',
      secondaryButton: 'rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60',
      infoBox: 'rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-xs text-slate-200',
    };
  }

  return {
    shell: 'space-y-4',
    surface: 'rounded-2xl border border-slate-200 bg-white p-4',
    muted: 'text-xs text-slate-600',
    text: 'text-sm text-slate-900',
    label: 'mb-1 block text-xs font-medium text-slate-500',
    input: 'w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-sky-400',
    textarea: 'w-full rounded-xl border border-slate-300 bg-white px-3 py-3 font-mono text-xs leading-6 text-slate-900 outline-none transition focus:border-sky-400',
    chip: 'rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-700',
    chipEmpty: 'rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-[11px] text-slate-500',
    subtleButton: 'rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-700 transition-colors hover:bg-slate-50',
    primaryButton: 'rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400',
    secondaryButton: 'rounded-xl border border-amber-300 bg-white px-4 py-2 text-sm font-medium text-amber-900 transition hover:border-amber-400 hover:bg-amber-100 disabled:cursor-not-allowed disabled:border disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400',
    infoBox: 'rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700',
  };
}

function resultBoxClasses(theme: 'light' | 'dark', tone: ScenePatchStatusMessage['tone']) {
  if (theme === 'dark') {
    if (tone === 'error') {
      return 'rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200';
    }
    if (tone === 'success') {
      return 'rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200';
    }
    return 'rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-xs text-slate-200';
  }

  if (tone === 'error') {
    return 'rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700';
  }
  if (tone === 'success') {
    return 'rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700';
  }
  return 'rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700';
}

export function parseScenePatchJson(scenePatchJson: string): {
  patch: StoryboardScenePatchPayload | null;
  error: string | null;
} {
  if (!scenePatchJson.trim()) {
    return { patch: null, error: null };
  }
  try {
    return {
      patch: JSON.parse(scenePatchJson) as StoryboardScenePatchPayload,
      error: null,
    };
  } catch (error) {
    return {
      patch: null,
      error: error instanceof Error ? error.message : 'scene patch JSON 無法解析',
    };
  }
}

export function buildScenePatchSummary(
  patch: StoryboardScenePatchPayload | null | undefined,
  fallbackSceneId: string,
): ScenePatchSummary | null {
  if (!patch) return null;
  const workloadSnapshot = patch.object_workload_snapshot || null;
  const impactRegionBBox = workloadSnapshot?.impact_region_bbox;
  const impactRegionBBoxLabel = impactRegionBBox
    ? `x=${impactRegionBBox.x ?? 0}, y=${impactRegionBBox.y ?? 0}, w=${impactRegionBBox.width ?? 0}, h=${impactRegionBBox.height ?? 0}`
    : undefined;
  return {
    sourceSceneId: patch.source_scene_id || fallbackSceneId || '-',
    objectAssetCount: Array.isArray(patch.object_assets) ? patch.object_assets.length : 0,
    usageBindingCount: Array.isArray(patch.object_reuse_plan?.usage_bindings)
      ? patch.object_reuse_plan.usage_bindings.length
      : Array.isArray(patch.object_reuse_plan?.usage_scene_ids)
        ? patch.object_reuse_plan.usage_scene_ids.length
        : 0,
    impactRegionMode: workloadSnapshot?.impact_region_mode,
    qualityGateState: workloadSnapshot?.quality_gate_state,
    affectedObjectCount: Array.isArray(workloadSnapshot?.affected_object_instance_ids)
      ? workloadSnapshot.affected_object_instance_ids.length
      : 0,
    impactRegionBBoxLabel,
  };
}

export function scenePatchResultMessage(
  message: string | null | undefined,
): ScenePatchStatusMessage | null {
  if (!message) return null;
  return {
    tone: message.includes('失敗') ? 'error' : 'success',
    message,
  };
}

export function ScenePatchConsole({
  theme = 'light',
  title = '場景 Patch 操作',
  description,
  patchMode,
  patch,
  patchJson = '',
  onPatchJsonChange,
  patchError,
  summary,
  sceneId,
  onSceneIdChange,
  sceneIdPlaceholder = '例如：SC_PATCH_01',
  onClearPatch,
  pdAction,
  mmsAction,
}: ScenePatchConsoleProps) {
  const styles = panelClasses(theme);
  const patchJsonPreview = useMemo(() => {
    if (patchMode === 'editable') return patchJson;
    if (!patch) return '';
    return JSON.stringify(patch, null, 2);
  }, [patch, patchJson, patchMode]);

  return (
    <div className={styles.shell}>
      <div className="flex flex-col gap-2 xl:flex-row xl:items-start xl:justify-between">
        <div className="space-y-1">
          <h3 className={cx('text-sm font-semibold', styles.text)}>{title}</h3>
          <p className={cx('max-w-3xl leading-5', styles.muted)}>{description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {summary ? (
            <>
              <span className={styles.chip}>來源場景：{summary.sourceSceneId}</span>
              <span className={styles.chip}>物件資產：{summary.objectAssetCount}</span>
              <span className={styles.chip}>場景綁定：{summary.usageBindingCount}</span>
              {summary.impactRegionMode ? (
                <span className={styles.chip}>影響區：{summary.impactRegionMode}</span>
              ) : null}
              {summary.qualityGateState ? (
                <span className={styles.chip}>Gate：{summary.qualityGateState}</span>
              ) : null}
              {summary.affectedObjectCount ? (
                <span className={styles.chip}>關聯物件：{summary.affectedObjectCount}</span>
              ) : null}
              {summary.impactRegionBBoxLabel ? (
                <span className={styles.chip}>BBox：{summary.impactRegionBBoxLabel}</span>
              ) : null}
            </>
          ) : (
            <span className={styles.chipEmpty}>
              {patchMode === 'editable' ? '尚未貼上 scene patch JSON' : '目前沒有可套用的 scene patch'}
            </span>
          )}
        </div>
      </div>

      <div className={cx('grid gap-4', pdAction && mmsAction ? 'xl:grid-cols-[1.15fr,0.85fr]' : 'xl:grid-cols-[1fr,0.85fr]')}>
        <div className={styles.surface}>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className={cx('text-sm font-medium', styles.text)}>storyboard_scene_patch</div>
              <div className={cx('mt-1', styles.muted)}>
                {patchMode === 'editable'
                  ? '貼上 LAF / ComfyUI 執行控制台輸出的 patch JSON。'
                  : '這份 patch 由當前綁定投影自動生成，作為顯式套用的唯一來源。'}
              </div>
            </div>
            {patchMode === 'editable' && onClearPatch ? (
              <button type="button" onClick={onClearPatch} className={styles.subtleButton}>
                清空
              </button>
            ) : null}
          </div>

          <div className="space-y-3">
            <div>
              <label className={styles.label}>scene_id</label>
              <input
                value={sceneId}
                onChange={(event) => onSceneIdChange(event.target.value)}
                placeholder={sceneIdPlaceholder}
                className={styles.input}
              />
            </div>
            <div>
              <label className={styles.label}>
                {patchMode === 'editable' ? 'Patch JSON' : 'Patch 預覽'}
              </label>
              <textarea
                value={patchJsonPreview}
                onChange={(event) => onPatchJsonChange?.(event.target.value)}
                readOnly={patchMode === 'derived'}
                placeholder={patchMode === 'editable' ? '貼上 {"source_scene_id":"SC_01", ... }' : '目前沒有可顯示的 patch'}
                className={cx(styles.textarea, patchMode === 'derived' && 'cursor-default')}
              />
            </div>
            {patchError ? (
              <div className={resultBoxClasses(theme, 'error')}>
                scene patch 解析失敗：{patchError}
              </div>
            ) : null}
          </div>
        </div>

        <div className="space-y-4">
          {pdAction ? (
            <div className={styles.surface}>
              <div className="mb-3">
                <div className={cx('text-sm font-medium', styles.text)}>套用到 PD Storyboard</div>
                <div className={cx('mt-1', styles.muted)}>
                  {pdAction.description || '將 scene patch 回寫到指定 PD session 的 storyboard artifact。'}
                </div>
              </div>
              <div className="space-y-3">
                <div>
                  <label className={styles.label}>PD session_id</label>
                  <input
                    value={pdAction.sessionId}
                    onChange={(event) => pdAction.onSessionIdChange(event.target.value)}
                    placeholder={pdAction.sessionIdPlaceholder || '例如：ds_xxx'}
                    className={styles.input}
                    readOnly={pdAction.sessionIdReadOnly}
                  />
                </div>
                {pdAction.hideArtifactId ? null : (
                  <div>
                    <label className={styles.label}>artifact_id（可留空）</label>
                    <input
                      value={pdAction.artifactId || ''}
                      onChange={(event) => pdAction.onArtifactIdChange?.(event.target.value)}
                      placeholder={pdAction.artifactPlaceholder || '留空時會使用最新 storyboard artifact'}
                      className={styles.input}
                    />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => void pdAction.onApply()}
                  disabled={pdAction.applying}
                  className={styles.primaryButton}
                >
                  {pdAction.applying ? '套用中…' : (pdAction.buttonLabel || '套用到 PD Storyboard')}
                </button>
                {pdAction.result ? (
                  <div className={cx(resultBoxClasses(theme, pdAction.result.tone), 'whitespace-pre-wrap leading-5')}>
                    {pdAction.result.message}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {mmsAction ? (
            <div className={styles.surface}>
              <div className="mb-3">
                <div className={cx('text-sm font-medium', styles.text)}>套用到 MMS Storyboard</div>
                <div className={cx('mt-1', styles.muted)}>
                  {mmsAction.description || '將 scene patch 套到 inline storyboard，更新後 JSON 直接回填。'}
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <label className={styles.label}>Storyboard JSON</label>
                  {mmsAction.onResetStoryboard ? (
                    <button type="button" onClick={mmsAction.onResetStoryboard} className={styles.subtleButton}>
                      重設範本
                    </button>
                  ) : null}
                </div>
                <textarea
                  value={mmsAction.storyboardJson}
                  onChange={(event) => mmsAction.onStoryboardJsonChange(event.target.value)}
                  className={cx(styles.textarea, 'min-h-[180px]')}
                  placeholder='{"workspace_id":"ws_demo","scenes":[{"scene_id":"sc01"}]}'
                />
                <button
                  type="button"
                  onClick={() => void mmsAction.onApply()}
                  disabled={mmsAction.applying}
                  className={styles.secondaryButton}
                >
                  {mmsAction.applying ? '套用中…' : (mmsAction.buttonLabel || '套用到 MMS Storyboard')}
                </button>
                {mmsAction.result ? (
                  <div className={cx(resultBoxClasses(theme, mmsAction.result.tone), 'whitespace-pre-wrap leading-5')}>
                    {mmsAction.result.message}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {!pdAction && !mmsAction ? (
            <div className={styles.infoBox}>
              目前這個入口只提供 patch 觀測，尚未掛入可套用目標。
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
