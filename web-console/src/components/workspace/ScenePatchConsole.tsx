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

export function buildScenePatchFailureText(error: unknown) {
  const detail = error instanceof Error ? error.message : String(error);
  return `Scene patch 套用失敗：${detail}`;
}

export type ScenePatchActionField =
  | {
    kind: 'text';
    id: string;
    label: string;
    value: string;
    onChange?: (value: string) => void;
    placeholder?: string;
    readOnly?: boolean;
    hidden?: boolean;
  }
  | {
    kind: 'textarea';
    id: string;
    label: string;
    value: string;
    onChange?: (value: string) => void;
    placeholder?: string;
    readOnly?: boolean;
    rows?: number;
    hidden?: boolean;
  }
  | {
    kind: 'button';
    id: string;
    label: string;
    onClick: () => void;
    hidden?: boolean;
  };

export interface ScenePatchActionConfig {
  id: string;
  title: string;
  description?: string;
  applying: boolean;
  result?: ScenePatchStatusMessage | null;
  onApply: () => void | Promise<void>;
  buttonLabel?: string;
  disabled?: boolean;
  disabledReason?: string | null;
  variant?: 'primary' | 'secondary';
  fields?: ScenePatchActionField[];
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
  objectAction?: ScenePatchActionConfig | null;
  objectActions?: ScenePatchActionConfig[];
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
  objectAction,
  objectActions = [],
}: ScenePatchConsoleProps) {
  const styles = panelClasses(theme);
  const patchJsonPreview = useMemo(() => {
    if (patchMode === 'editable') return patchJson;
    if (!patch) return '';
    return JSON.stringify(patch, null, 2);
  }, [patch, patchJson, patchMode]);
  const actionItems = useMemo(
    () => [
      ...(objectAction ? [objectAction] : []),
      ...objectActions,
    ],
    [objectAction, objectActions],
  );

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

      <div className={cx('grid gap-4', actionItems.length > 1 ? 'xl:grid-cols-[1.15fr,0.85fr]' : 'xl:grid-cols-[1fr,0.85fr]')}>
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
          {actionItems.map((action) => (
            <div key={action.id} className={styles.surface}>
              <div className="mb-3">
                <div className={cx('text-sm font-medium', styles.text)}>{action.title}</div>
                {action.description ? (
                  <div className={cx('mt-1', styles.muted)}>{action.description}</div>
                ) : null}
              </div>
              <div className="space-y-3">
                {(action.fields || []).map((field) => {
                  if (field.hidden) return null;
                  if (field.kind === 'button') {
                    return (
                      <button
                        key={field.id}
                        type="button"
                        onClick={field.onClick}
                        className={styles.subtleButton}
                      >
                        {field.label}
                      </button>
                    );
                  }
                  if (field.kind === 'textarea') {
                    return (
                      <div key={field.id}>
                        <label className={styles.label}>{field.label}</label>
                        <textarea
                          value={field.value}
                          onChange={(event) => field.onChange?.(event.target.value)}
                          className={cx(styles.textarea, 'min-h-[180px]')}
                          placeholder={field.placeholder}
                          readOnly={field.readOnly}
                          rows={field.rows}
                        />
                      </div>
                    );
                  }
                  return (
                    <div key={field.id}>
                      <label className={styles.label}>{field.label}</label>
                      <input
                        value={field.value}
                        onChange={(event) => field.onChange?.(event.target.value)}
                        placeholder={field.placeholder}
                        className={styles.input}
                        readOnly={field.readOnly}
                      />
                    </div>
                  );
                })}
                {action.disabled && action.disabledReason ? (
                  <div className={resultBoxClasses(theme, 'info')}>
                    {action.disabledReason}
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={() => void action.onApply()}
                  disabled={action.applying || action.disabled}
                  className={action.variant === 'secondary' ? styles.secondaryButton : styles.primaryButton}
                >
                  {action.applying ? '套用中…' : (action.buttonLabel || action.title)}
                </button>
                {action.result ? (
                  <div className={cx(resultBoxClasses(theme, action.result.tone), 'whitespace-pre-wrap leading-5')}>
                    {action.result.message}
                  </div>
                ) : null}
              </div>
            </div>
          ))}

          {actionItems.length === 0 ? (
            <div className={styles.infoBox}>
              No scene patch action is available for this context.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
