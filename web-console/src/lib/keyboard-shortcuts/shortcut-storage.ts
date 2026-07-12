import { settingsApi } from '@/app/settings/utils/settingsApi';
import type {
  KeyboardShortcutCatalogItem,
  KeyboardShortcutProfile,
  KeyboardShortcutProfileResponse,
} from './shortcut-types';

type KeyboardShortcutCatalogApiItem = NonNullable<KeyboardShortcutProfileResponse['catalog']>[number];

export const EMPTY_KEYBOARD_SHORTCUT_PROFILE: KeyboardShortcutProfile = {
  schema_version: 1,
  bindings: [],
};

function normalizeCatalogItem(item: KeyboardShortcutCatalogApiItem): KeyboardShortcutCatalogItem | null {
  if (!item || !item.binding_id || !item.command_id || !item.label || !item.owner_type || !item.scope) {
    return null;
  }
  return {
    bindingId: item.binding_id,
    commandId: item.command_id,
    label: item.label,
    ownerType: item.owner_type,
    ownerId: item.owner_id || undefined,
    ownerLabel: item.owner_label || undefined,
    defaultShortcut: item.default_shortcut || undefined,
    scope: item.scope,
    source: item.source,
    metadata: item.metadata,
  };
}

export function normalizeKeyboardShortcutResponse(
  response: Partial<KeyboardShortcutProfileResponse> | null | undefined,
): {
  profile: KeyboardShortcutProfile;
  catalog: KeyboardShortcutCatalogItem[];
  updatedAt?: string | null;
} {
  const profile: KeyboardShortcutProfile = {
    schema_version: 1,
    bindings: Array.isArray(response?.bindings) ? response.bindings : [],
  };
  return {
    profile,
    catalog: Array.isArray(response?.catalog)
      ? response.catalog.map(normalizeCatalogItem).filter((item): item is KeyboardShortcutCatalogItem => Boolean(item))
      : [],
    updatedAt: response?.updated_at,
  };
}

export async function loadKeyboardShortcutProfile(workspaceId?: string) {
  try {
    const workspaceQuery = workspaceId
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : '';
    const response = await settingsApi.get<KeyboardShortcutProfileResponse>(
      `/api/v1/system-settings/keyboard-shortcuts${workspaceQuery}`,
      { silent: true },
    );
    return normalizeKeyboardShortcutResponse(response);
  } catch {
    return {
      profile: EMPTY_KEYBOARD_SHORTCUT_PROFILE,
      catalog: [],
      updatedAt: null,
    };
  }
}

export async function saveKeyboardShortcutProfile(profile: KeyboardShortcutProfile) {
  const response = await settingsApi.put<KeyboardShortcutProfileResponse>(
    '/api/v1/system-settings/keyboard-shortcuts',
    profile,
  );
  return normalizeKeyboardShortcutResponse(response);
}
