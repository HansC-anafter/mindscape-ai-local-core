'use client';

import React from 'react';
import {
  AlertTriangle,
  Ban,
  Keyboard,
  RotateCcw,
  Save,
} from 'lucide-react';

import { t } from '../../../../lib/i18n';
import { useKeyboardShortcuts } from '../../../../lib/keyboard-shortcuts';
import {
  eventToShortcut,
  formatShortcutForDisplay,
  normalizeShortcut,
} from '../../../../lib/keyboard-shortcuts/shortcut-normalization';
import {
  loadKeyboardShortcutProfile,
  saveKeyboardShortcutProfile,
} from '../../../../lib/keyboard-shortcuts/shortcut-storage';
import type {
  KeyboardShortcutBindingOverride,
  KeyboardShortcutCatalogItem,
  KeyboardShortcutCommand,
} from '../../../../lib/keyboard-shortcuts/shortcut-types';
import { showNotification } from '../../hooks/useSettingsNotification';
import { Card } from '../Card';

interface ShortcutRow {
  bindingId: string;
  commandId: string;
  label: string;
  ownerType: 'core' | 'pack';
  ownerId?: string;
  ownerLabel?: string;
  defaultShortcut?: string;
  currentShortcut?: string;
  disabled: boolean;
  scope: string;
  source: string;
}

const ALL_OWNER_FILTER = '__all__';

function commandToCatalogItem(command: KeyboardShortcutCommand): KeyboardShortcutCatalogItem {
  return {
    bindingId: command.bindingId,
    commandId: command.commandId,
    label: command.label,
    ownerType: command.ownerType,
    ownerId: command.ownerId,
    ownerLabel: command.ownerLabel,
    defaultShortcut: command.defaultShortcut,
    scope: command.scope,
    source: 'runtime.registry',
  };
}

function bindingKey(bindingId: string): string {
  return bindingId;
}

function ownerFilterValue(row: ShortcutRow): string {
  return `${row.ownerType}:${row.ownerId || row.ownerType}`;
}

function buildRows(
  catalog: KeyboardShortcutCatalogItem[],
  overrides: KeyboardShortcutBindingOverride[],
): ShortcutRow[] {
  const overrideByBinding = new Map(overrides.map((override) => [override.binding_id, override]));
  return catalog
    .map((item): ShortcutRow => {
      const override = overrideByBinding.get(item.bindingId);
      return {
        bindingId: item.bindingId,
        commandId: item.commandId,
        label: item.label,
        ownerType: item.ownerType,
        ownerId: item.ownerId,
        ownerLabel: item.ownerLabel,
        defaultShortcut: item.defaultShortcut,
        currentShortcut: override?.shortcut || item.defaultShortcut,
        disabled: Boolean(override?.disabled),
        scope: item.scope,
        source: item.source,
      };
    })
    .sort((left, right) => (
      left.ownerType.localeCompare(right.ownerType)
      || (left.ownerLabel || left.ownerId || '').localeCompare(right.ownerLabel || right.ownerId || '')
      || left.label.localeCompare(right.label)
      || left.bindingId.localeCompare(right.bindingId)
    ));
}

function detectConflicts(rows: ShortcutRow[]): Set<string> {
  const byScopeAndShortcut = new Map<string, string[]>();
  rows.forEach((row) => {
    if (row.disabled || !row.currentShortcut) {
      return;
    }
    const normalized = normalizeShortcut(row.currentShortcut);
    if (!normalized) {
      return;
    }
    const key = `${row.scope}:${normalized.canonical}`;
    const values = byScopeAndShortcut.get(key) || [];
    values.push(row.bindingId);
    byScopeAndShortcut.set(key, values);
  });
  const conflicts = new Set<string>();
  byScopeAndShortcut.forEach((bindingIds) => {
    if (bindingIds.length > 1) {
      bindingIds.forEach((bindingId) => conflicts.add(bindingId));
    }
  });
  return conflicts;
}

function rowsToProfileBindings(rows: ShortcutRow[]): KeyboardShortcutBindingOverride[] {
  return rows
    .filter((row) => (
      row.disabled
      || (row.currentShortcut || undefined) !== (row.defaultShortcut || undefined)
    ))
    .map((row) => ({
      binding_id: row.bindingId,
      command_id: row.commandId,
      owner_type: row.ownerType,
      owner_id: row.ownerId,
      shortcut: row.disabled ? null : row.currentShortcut || null,
      disabled: row.disabled,
    }));
}

export function KeyboardShortcutsSettingsPanel() {
  const {
    commands,
    setProfile,
  } = useKeyboardShortcuts();
  const [catalog, setCatalog] = React.useState<KeyboardShortcutCatalogItem[]>([]);
  const [rows, setRows] = React.useState<ShortcutRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [listeningBindingId, setListeningBindingId] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState('');
  const [selectedOwnerFilter, setSelectedOwnerFilter] = React.useState(ALL_OWNER_FILTER);

  const reload = React.useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await loadKeyboardShortcutProfile();
      const runtimeCatalog = commands.map(commandToCatalogItem);
      const mergedCatalog = new Map<string, KeyboardShortcutCatalogItem>();
      result.catalog.forEach((item) => mergedCatalog.set(item.bindingId, item));
      runtimeCatalog.forEach((item) => mergedCatalog.set(item.bindingId, item));
      const nextCatalog = Array.from(mergedCatalog.values());
      setCatalog(nextCatalog);
      setRows(buildRows(nextCatalog, result.profile.bindings));
      setProfile(result.profile);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load keyboard shortcuts';
      setLoadError(message);
    } finally {
      setLoading(false);
    }
  }, [commands, setProfile]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const conflicts = React.useMemo(() => detectConflicts(rows), [rows]);
  const ownerOptions = React.useMemo(() => {
    const byOwner = new Map<string, { value: string; label: string; count: number }>();
    rows.forEach((row) => {
      const value = ownerFilterValue(row);
      const option = byOwner.get(value) || {
        value,
        label: row.ownerLabel || row.ownerId || row.ownerType,
        count: 0,
      };
      option.count += 1;
      byOwner.set(value, option);
    });
    return Array.from(byOwner.values()).sort((left, right) => left.label.localeCompare(right.label));
  }, [rows]);
  React.useEffect(() => {
    if (
      selectedOwnerFilter !== ALL_OWNER_FILTER
      && !ownerOptions.some((option) => option.value === selectedOwnerFilter)
    ) {
      setSelectedOwnerFilter(ALL_OWNER_FILTER);
    }
  }, [ownerOptions, selectedOwnerFilter]);
  const ownerScopedRows = React.useMemo(() => (
    selectedOwnerFilter === ALL_OWNER_FILTER
      ? rows
      : rows.filter((row) => ownerFilterValue(row) === selectedOwnerFilter)
  ), [rows, selectedOwnerFilter]);
  const filteredRows = React.useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return ownerScopedRows;
    }
    return ownerScopedRows.filter((row) => (
      row.label.toLowerCase().includes(normalizedQuery)
      || row.bindingId.toLowerCase().includes(normalizedQuery)
      || (row.ownerLabel || row.ownerId || '').toLowerCase().includes(normalizedQuery)
    ));
  }, [ownerScopedRows, query]);

  const updateRow = React.useCallback((bindingId: string, update: Partial<ShortcutRow>) => {
    setRows((currentRows) => currentRows.map((row) => (
      row.bindingId === bindingId ? { ...row, ...update } : row
    )));
  }, []);

  const handleCapture = React.useCallback((row: ShortcutRow, event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (listeningBindingId !== row.bindingId) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const shortcut = eventToShortcut(event.nativeEvent);
    if (!shortcut) {
      return;
    }
    updateRow(row.bindingId, {
      currentShortcut: shortcut.canonical,
      disabled: false,
    });
    setListeningBindingId(null);
  }, [listeningBindingId, updateRow]);

  const handleSave = React.useCallback(async () => {
    if (conflicts.size > 0) {
      showNotification('error', t('keyboardShortcutsConflict' as any));
      return;
    }
    setSaving(true);
    try {
      const saved = await saveKeyboardShortcutProfile({
        schema_version: 1,
        bindings: rowsToProfileBindings(rows),
      });
      setRows(buildRows(catalog, saved.profile.bindings));
      setProfile(saved.profile);
      showNotification('success', t('keyboardShortcutsSaved' as any));
    } catch (error) {
      showNotification(
        'error',
        error instanceof Error ? error.message : t('keyboardShortcutsSaveFailed' as any),
      );
    } finally {
      setSaving(false);
    }
  }, [catalog, conflicts.size, rows, setProfile]);

  return (
    <Card className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-default pb-4 dark:border-gray-700 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Keyboard aria-hidden className="h-5 w-5 text-accent" />
            <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
              {t('keyboardShortcuts' as any)}
            </h2>
          </div>
          <p className="mt-1 text-sm text-secondary dark:text-gray-400">
            {t('keyboardShortcutsDescription' as any)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setRows(buildRows(catalog, []));
              setListeningBindingId(null);
            }}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-default px-3 text-sm text-primary transition hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
          >
            <RotateCcw aria-hidden className="h-4 w-4" />
            {t('keyboardShortcutsResetAll' as any)}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || conflicts.size > 0}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Save aria-hidden className="h-4 w-4" />
            {saving ? t('savingPortConfig' as any) : t('keyboardShortcutsSave' as any)}
          </button>
        </div>
      </div>

      {loadError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {loadError}
        </div>
      ) : null}

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('keyboardShortcutsSearch' as any)}
          className="h-9 w-full rounded-md border border-default bg-surface-primary px-3 text-sm text-primary outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 sm:max-w-sm"
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          <label className="flex items-center gap-2 text-xs text-secondary dark:text-gray-400">
            <span className="whitespace-nowrap">{t('keyboardShortcutsPackFilter' as any)}</span>
            <select
              value={selectedOwnerFilter}
              onChange={(event) => setSelectedOwnerFilter(event.target.value)}
              className="h-9 min-w-44 rounded-md border border-default bg-surface-primary px-2 text-sm text-primary outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
            >
              <option value={ALL_OWNER_FILTER}>
                {t('keyboardShortcutsAllInstalledPacks' as any)}
              </option>
              {ownerOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} ({option.count})
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs text-tertiary dark:text-gray-500">
            {filteredRows.length} / {ownerScopedRows.length}
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-default dark:border-gray-700">
        <div className="grid grid-cols-[minmax(180px,1.4fr)_minmax(120px,0.8fr)_minmax(96px,0.5fr)_minmax(140px,0.7fr)_minmax(160px,0.8fr)] gap-0 border-b border-default bg-surface-secondary text-xs font-medium uppercase tracking-wide text-tertiary dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
          <div className="px-3 py-2">{t('keyboardShortcutsCommand' as any)}</div>
          <div className="px-3 py-2">{t('keyboardShortcutsOwner' as any)}</div>
          <div className="px-3 py-2">{t('keyboardShortcutsDefault' as any)}</div>
          <div className="px-3 py-2">{t('keyboardShortcutsCurrent' as any)}</div>
          <div className="px-3 py-2">{t('keyboardShortcutsActions' as any)}</div>
        </div>
        {loading ? (
          <div className="px-3 py-5 text-sm text-secondary dark:text-gray-400">
            {t('loading' as any)}
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="px-3 py-5 text-sm text-secondary dark:text-gray-400">
            {t('keyboardShortcutsEmpty' as any)}
          </div>
        ) : (
          filteredRows.map((row) => {
            const conflict = conflicts.has(row.bindingId);
            const displayShortcut = row.disabled
              ? t('keyboardShortcutsDisabled' as any)
              : formatShortcutForDisplay(row.currentShortcut) || '-';
            return (
              <div
                key={bindingKey(row.bindingId)}
                className="grid grid-cols-[minmax(180px,1.4fr)_minmax(120px,0.8fr)_minmax(96px,0.5fr)_minmax(140px,0.7fr)_minmax(160px,0.8fr)] border-b border-default text-sm last:border-b-0 dark:border-gray-700"
              >
                <div className="min-w-0 px-3 py-2">
                  <div className="truncate font-medium text-primary dark:text-gray-100">
                    {row.label}
                  </div>
                  <div className="truncate text-xs text-tertiary dark:text-gray-500">
                    {row.bindingId}
                  </div>
                </div>
                <div className="min-w-0 px-3 py-2 text-secondary dark:text-gray-400">
                  <div className="truncate">{row.ownerLabel || row.ownerId || row.ownerType}</div>
                  <div className="truncate text-xs text-tertiary dark:text-gray-500">{row.source}</div>
                </div>
                <div className="px-3 py-2 font-mono text-xs text-secondary dark:text-gray-300">
                  {formatShortcutForDisplay(row.defaultShortcut) || '-'}
                </div>
                <div className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className={`font-mono text-xs ${row.disabled ? 'text-tertiary line-through dark:text-gray-500' : 'text-primary dark:text-gray-100'}`}>
                      {displayShortcut}
                    </span>
                    {conflict ? (
                      <span className="inline-flex items-center gap-1 rounded-sm bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-950/50 dark:text-red-300">
                        <AlertTriangle aria-hidden className="h-3 w-3" />
                        {t('keyboardShortcutsConflictShort' as any)}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 px-3 py-2">
                  <button
                    type="button"
                    onClick={() => setListeningBindingId(row.bindingId)}
                    onKeyDown={(event) => handleCapture(row, event)}
                    className="inline-flex h-7 items-center rounded-sm border border-default px-2 text-xs text-primary transition hover:bg-surface-secondary focus:outline-none focus:ring-2 focus:ring-accent/30 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
                  >
                    {listeningBindingId === row.bindingId
                      ? t('keyboardShortcutsListening' as any)
                      : t('keyboardShortcutsCapture' as any)}
                  </button>
                  <button
                    type="button"
                    onClick={() => updateRow(row.bindingId, {
                      currentShortcut: row.defaultShortcut,
                      disabled: false,
                    })}
                    className="inline-flex h-7 items-center rounded-sm border border-default px-2 text-xs text-primary transition hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
                  >
                    <RotateCcw aria-hidden className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => updateRow(row.bindingId, { disabled: !row.disabled })}
                    className="inline-flex h-7 items-center rounded-sm border border-default px-2 text-xs text-primary transition hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
                  >
                    <Ban aria-hidden className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
