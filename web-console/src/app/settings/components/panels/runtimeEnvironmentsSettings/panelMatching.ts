import type { RuntimeEnvironment, SettingsPanel } from './types';

const slugifyRuntimeCode = (value: string | null | undefined): string | null => {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return null;
  const slug = text
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return slug || null;
};

const getRuntimeMatchCodes = (runtime: RuntimeEnvironment | undefined): string[] => {
  if (!runtime) {
    return [];
  }
  const metadata = runtime.metadata || {};
  const candidates = [
    runtime.id,
    slugifyRuntimeCode(runtime.id),
    runtime.name,
    slugifyRuntimeCode(runtime.name),
    metadata.runtime_type,
    slugifyRuntimeCode(metadata.runtime_type),
    metadata.capability_code,
    slugifyRuntimeCode(metadata.capability_code),
  ];
  return Array.from(
    new Set(
      candidates
        .map((value) => String(value || '').trim())
        .filter(Boolean)
    )
  );
};

const normalizeMatchCode = (value: string | null | undefined): string | null => {
  const text = String(value || '').trim();
  if (!text) {
    return null;
  }
  return slugifyRuntimeCode(text) || text.toLowerCase();
};

const getPanelMatchCodes = (panel: SettingsPanel): string[] => {
  const candidates = [
    panel.capabilityCode,
    panel.componentCode,
    panel.title,
    panel.displayMode,
  ];
  return Array.from(
    new Set(
      candidates
        .map((value) => normalizeMatchCode(value))
        .filter(Boolean) as string[]
    )
  );
};

const getSignificantMatchTokens = (value: string): string[] => {
  const ignored = new Set(['core', 'local', 'modal', 'panel', 'runtime', 'settings']);
  return value
    .split('_')
    .map((token) => token.trim())
    .filter((token) => token.length >= 4 && !ignored.has(token));
};

export const isRuntimeScopedSettingsPanel = (panel: SettingsPanel): boolean => {
  return panel.displayMode === 'runtime_modal' || Boolean(panel.showWhen?.runtimeCodes?.length);
};

const panelMatchesRuntime = (
  panel: SettingsPanel,
  runtime: RuntimeEnvironment | undefined,
): boolean => {
  if (!runtime) {
    return false;
  }
  const runtimeCodes = new Set(
    getRuntimeMatchCodes(runtime)
      .map((value) => normalizeMatchCode(value))
      .filter(Boolean) as string[]
  );
  const requiredCodes = (panel.showWhen?.runtimeCodes || [])
    .map((value) => normalizeMatchCode(value))
    .filter(Boolean) as string[];

  if (requiredCodes.length) {
    return requiredCodes.some((code) => runtimeCodes.has(code));
  }

  if (panel.displayMode === 'runtime_modal') {
    return true;
  }

  const panelCodes = getPanelMatchCodes(panel);
  return panelCodes.some((panelCode) =>
    Array.from(runtimeCodes).some((runtimeCode) =>
      panelCode === runtimeCode
      || panelCode.startsWith(`${runtimeCode}_`)
      || panelCode.endsWith(`_${runtimeCode}`)
      || getSignificantMatchTokens(panelCode).some((token) =>
        getSignificantMatchTokens(runtimeCode).includes(token)
      )
    )
  );
};

export const resolveRuntimeModalPanels = (
  runtime: RuntimeEnvironment | undefined,
  panels: SettingsPanel[],
): SettingsPanel[] => {
  if (!runtime) {
    return [];
  }

  const seen = new Set<string>();
  return panels.filter((panel) => {
    if (!isRuntimeScopedSettingsPanel(panel) && panel.section !== 'workflow-engines') {
      return false;
    }
    if (!panelMatchesRuntime(panel, runtime)) {
      return false;
    }
    const key = `${panel.capabilityCode}:${panel.componentCode}:${panel.section || ''}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

export const shouldRenderSettingsPanelInline = (panel: SettingsPanel): boolean => {
  return !isRuntimeScopedSettingsPanel(panel);
};

export const shouldRenderWorkflowPanelInline = (
  panel: SettingsPanel,
  runtimes: RuntimeEnvironment[],
): boolean => {
  return !runtimes.some((runtime) => panelMatchesRuntime(panel, runtime));
};
