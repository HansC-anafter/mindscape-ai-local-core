import type { PlaybookListItem, RecentPlaybookView } from './playbookDetailTypes';

export const RECENT_PLAYBOOKS_KEY = 'playbook_recent_views';
export const RECENT_PLAYBOOKS_STORAGE_LIMIT = 10;
export const RECENT_PLAYBOOKS_DISPLAY_LIMIT = 5;

type RecentStorageReader = Pick<Storage, 'getItem'>;
type RecentStorageWriter = Pick<Storage, 'getItem' | 'setItem'>;

export function getBrowserLocalStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

export function parseRecentPlaybookViews(stored: string | null): RecentPlaybookView[] {
  if (!stored) {
    return [];
  }
  const parsed = JSON.parse(stored);
  return Array.isArray(parsed) ? parsed : [];
}

export function selectRecentPlaybooks(
  recent: RecentPlaybookView[],
  currentPlaybookCode: string,
  limit = RECENT_PLAYBOOKS_DISPLAY_LIMIT
): PlaybookListItem[] {
  return recent
    .filter((playbook) => playbook.playbook_code !== currentPlaybookCode)
    .slice(0, limit)
    .map((playbook) => ({
      playbook_code: playbook.playbook_code,
      name: playbook.name,
      description: playbook.description,
      icon: playbook.icon,
    }));
}

export function upsertRecentPlaybookView(
  recent: RecentPlaybookView[],
  playbookCode: string,
  metadata: Pick<PlaybookListItem, 'name' | 'description' | 'icon'>,
  viewedAt = new Date().toISOString()
): RecentPlaybookView[] {
  return [
    {
      playbook_code: playbookCode,
      name: metadata.name,
      description: metadata.description,
      icon: metadata.icon,
      viewed_at: viewedAt,
    },
    ...recent.filter((playbook) => playbook.playbook_code !== playbookCode),
  ].slice(0, RECENT_PLAYBOOKS_STORAGE_LIMIT);
}

export function readRecentPlaybookViews(storage: RecentStorageReader): RecentPlaybookView[] {
  return parseRecentPlaybookViews(storage.getItem(RECENT_PLAYBOOKS_KEY));
}

export function recordRecentPlaybookView(
  storage: RecentStorageWriter,
  playbookCode: string,
  metadata: Pick<PlaybookListItem, 'name' | 'description' | 'icon'>
): PlaybookListItem[] {
  const recent = upsertRecentPlaybookView(readRecentPlaybookViews(storage), playbookCode, metadata);
  storage.setItem(RECENT_PLAYBOOKS_KEY, JSON.stringify(recent));
  return selectRecentPlaybooks(recent, playbookCode);
}
