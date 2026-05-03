import type { MeetingNode, MeetingObjectActionEntry, MeetingObjectActionRole } from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

const ACTION_ROLES: MeetingObjectActionRole[] = [
  'source',
  'target',
  'character',
  'constraint',
  'baseline',
  'evidence',
];

function normalizeActionRole(value: unknown): MeetingObjectActionRole | null {
  const role = readString(value).toLowerCase();
  return ACTION_ROLES.includes(role as MeetingObjectActionRole)
    ? role as MeetingObjectActionRole
    : null;
}

function readRequiredRoles(value: unknown): MeetingObjectActionRole[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const roles: MeetingObjectActionRole[] = [];
  value.forEach((rawRole) => {
    const role = normalizeActionRole(rawRole);
    if (role && !roles.includes(role)) {
      roles.push(role);
    }
  });
  return roles;
}

export function getGuidanceRequiredRoles(node: MeetingNode | null): MeetingObjectActionRole[] {
  const metadata = isRecord(node?.metadata) ? node.metadata : {};
  const explicitRoles = readRequiredRoles(metadata.required_roles);
  if (explicitRoles.length > 0) {
    return explicitRoles;
  }
  return isRecord(metadata.target_ref) ? ['target'] : [];
}

export function getMissingCommandContextRoles(
  requiredRoles: MeetingObjectActionRole[],
  objectActionEntries: MeetingObjectActionEntry[],
): MeetingObjectActionRole[] {
  const presentRoles = new Set(objectActionEntries.map((entry) => entry.role));
  return requiredRoles.filter((role) => !presentRoles.has(role));
}

export function formatCommandContextRole(role: MeetingObjectActionRole): string {
  if (role === 'target') {
    return 'Target';
  }
  if (role === 'source') {
    return 'Source';
  }
  if (role === 'character') {
    return 'Character';
  }
  if (role === 'constraint') {
    return 'Constraint';
  }
  if (role === 'baseline') {
    return 'Baseline';
  }
  return 'Evidence';
}
