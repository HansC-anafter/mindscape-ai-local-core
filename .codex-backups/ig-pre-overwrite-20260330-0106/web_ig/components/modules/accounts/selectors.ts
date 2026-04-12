import type { ConnectedAccount, DiscoveredAccount } from './types';

export interface FilterOption {
  key: string;
  label: string;
  count: number;
}

export function filterConnectedAccounts(
  accounts: ConnectedAccount[],
  searchQuery: string
): ConnectedAccount[] {
  const q = (searchQuery || '').toLowerCase();
  return accounts.filter((account) =>
    account.channel_name.toLowerCase().includes(q) ||
    account.username?.toLowerCase().includes(q)
  );
}

export function filterDiscoveredAccounts(
  accounts: DiscoveredAccount[],
  searchQuery: string
): DiscoveredAccount[] {
  const q = (searchQuery || '').toLowerCase();
  return accounts.filter((account) =>
    account.handle.toLowerCase().includes(q) ||
    account.name?.toLowerCase().includes(q) ||
    account.bio?.toLowerCase().includes(q)
  );
}

export function buildSourceOptions(accounts: DiscoveredAccount[]): FilterOption[] {
  const byKey = new Map<string, { label: string; handles: Set<string> }>();

  accounts.forEach((acc) => {
    const handle = (acc.handle || '').trim();
    if (!handle) return;

    const keys = new Set<string>();
    (acc.sources || []).forEach((s) => {
      const key = (s.source_account_handle && s.source_account_handle.trim())
        ? `handle:${s.source_account_handle.trim()}`
        : 'unknown';
      keys.add(key);
    });

    keys.forEach((key) => {
      const label = key.startsWith('handle:') ? `@${key.slice('handle:'.length)}` : 'Unknown';
      const existing = byKey.get(key) || { label, handles: new Set<string>() };
      existing.handles.add(handle);
      byKey.set(key, existing);
    });
  });

  return Array.from(byKey.entries())
    .map(([key, v]) => ({ key, label: v.label, count: v.handles.size }))
    .sort((a, b) => b.count - a.count);
}

export function buildSeedOptions(accounts: DiscoveredAccount[], recentRuns: any[] = []): FilterOption[] {
  const byKey = new Map<string, { label: string; handles: Set<string> }>();

  // FIXED: Extract unique seeds directly from discovered accounts' sources (stable source)
  // This eliminates dependency on recentRuns which can be pushed out by newer executions.
  // The "9 is 9" guarantee now comes from the accounts data itself, not execution history.
  accounts.forEach((acc) => {
    const handle = (acc.handle || '').trim();
    if (!handle) return;

    const keys = new Set<string>();
    (acc.sources || []).forEach((s) => {
      const seed = (s.target_seed || '').trim();
      if (!seed) return;
      keys.add(`seed:${seed}`);
    });

    keys.forEach((key) => {
      const label = key.startsWith('seed:') ? key.slice('seed:'.length) : key;
      const existing = byKey.get(key) || { label, handles: new Set<string>() };
      existing.handles.add(handle);
      byKey.set(key, existing);
    });
  });

  // NOTE: recentRuns parameter is kept for backwards compatibility but no longer used.
  // Seeds are now derived exclusively from loaded accounts data.

  return Array.from(byKey.entries())
    .map(([key, v]) => ({ key, label: v.label, count: v.handles.size }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

export function filterTargets(
  accounts: DiscoveredAccount[],
  params: { sourceFilterKey: string; seedFilterKey: string }
): DiscoveredAccount[] {
  const { sourceFilterKey, seedFilterKey } = params;

  return accounts.filter((acc) => {
    const matchesSource = sourceFilterKey === 'all' ? true : (acc.sources || []).some((s) => {
      const key = (s.source_account_handle && s.source_account_handle.trim())
        ? `handle:${s.source_account_handle.trim()}`
        : 'unknown';
      return key === sourceFilterKey;
    });
    if (!matchesSource) return false;

    const matchesSeed = seedFilterKey === 'all' ? true : (acc.sources || []).some((s) => {
      const seed = (s.target_seed || '').trim();
      return seed ? `seed:${seed}` === seedFilterKey : false;
    });
    return matchesSeed;
  });
}

