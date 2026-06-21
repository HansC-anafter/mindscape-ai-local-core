import type { Playbook, PlaybooksByCapability } from './playbooksPageTypes';

export function extractCapabilityCode(playbook: Playbook): string | null {
  if (playbook.capability_code) {
    return playbook.capability_code;
  }

  if (playbook.playbook_code && playbook.playbook_code.includes('.')) {
    const parts = playbook.playbook_code.split('.');
    if (parts.length >= 2) {
      const potentialCapabilityCode = parts[0];
      if (potentialCapabilityCode.length > 2 && !potentialCapabilityCode.includes(' ')) {
        return potentialCapabilityCode;
      }
    }
  }

  return null;
}

export function getPlaybookBadge(playbook: Playbook): string {
  const source = playbook.playbook_code || playbook.name || 'PB';
  const badge = source.replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase();
  return badge || 'PB';
}

export function normalizePlaybookList(data: unknown): Playbook[] {
  return Array.isArray(data)
    ? data.filter((playbook) => playbook && playbook.playbook_code && playbook.name)
    : [];
}

export function filterPlaybooksBySearch(playbooks: Playbook[], searchTerm: string): Playbook[] {
  if (!searchTerm) {
    return playbooks;
  }
  const lowerSearch = searchTerm.toLowerCase();
  return playbooks.filter((playbook) =>
    (playbook.name && playbook.name.toLowerCase().includes(lowerSearch)) ||
    (playbook.description && playbook.description.toLowerCase().includes(lowerSearch))
  );
}

export function groupPlaybooksByCapability(playbooks: Playbook[]): PlaybooksByCapability {
  const groups: PlaybooksByCapability = {};

  playbooks.forEach((playbook) => {
    const capabilityCode = extractCapabilityCode(playbook) || 'system';
    if (!groups[capabilityCode]) {
      groups[capabilityCode] = [];
    }
    groups[capabilityCode].push(playbook);
  });

  if (!groups.system) {
    groups.system = [];
  }

  return groups;
}

export function getAvailableCapabilityCodes(playbooksByCapability: PlaybooksByCapability): string[] {
  return Object.entries(playbooksByCapability)
    .filter(([, playbooks]) => playbooks.length > 0)
    .map(([code]) => code);
}

export function buildWorkspaceTitle(playbookCode: string, now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');
  return `${playbookCode}_${year}${month}${day}_${hours}${minutes}${seconds}`;
}
