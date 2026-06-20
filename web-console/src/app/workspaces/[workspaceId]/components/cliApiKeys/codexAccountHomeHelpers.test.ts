import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import {
  CODEX_LOGIN_TIMEOUT_MS,
  CODEX_LOGOUT_TIMEOUT_MS,
  CODEX_PROBE_TIMEOUT_MS,
  codexAccountHomesRoot,
  errorMessageFromPayload,
  newCodexAccountHomePath,
  probeErrorCodeFromPayload,
  shortKey,
  shortRuntimeId,
} from './codexAccountHomeHelpers';
import type { AgentAuthActionResponse, CodexAccountHomeTarget } from './types';

const target = (codexHome: string): CodexAccountHomeTarget => ({
  runtime_id: 'runtime-codex_cli-abc123',
  login_email: 'person@example.test',
  account_key: 'account-key-1234567890',
  account_scope_type: 'personal',
  account_scope_label: 'Personal',
  account_scope_role: null,
  account_plan_type: 'plus',
  account_organization_id: null,
  account_organization_title: null,
  account_organization_count: null,
  codex_home: codexHome,
  auth_json_path: null,
  auth_mtime_ns: null,
  auth_size: null,
  has_access: true,
  has_refresh: true,
  probe_state: 'available',
  last_probe_error_code: null,
  last_probe_success_at: null,
  cooldown_until: null,
  last_error_code: null,
});

const response = (payload: Partial<AgentAuthActionResponse>): AgentAuthActionResponse => ({
  agent_id: 'codex_cli',
  workspace_id: 'workspace-1',
  action: 'probe',
  success: false,
  output: '',
  error: null,
  note: null,
  ...payload,
});

describe('codex account-home helpers', () => {
  it('preserves timeout constants', () => {
    expect(CODEX_LOGIN_TIMEOUT_MS).toBe(300_000);
    expect(CODEX_LOGOUT_TIMEOUT_MS).toBe(45_000);
    expect(CODEX_PROBE_TIMEOUT_MS).toBe(120_000);
  });

  it('reads payload messages by the established precedence', () => {
    expect(errorMessageFromPayload({ detail: 'detail wins', error: 'error' }, 'fallback')).toBe('detail wins');
    expect(errorMessageFromPayload({ error: 'error wins', note: 'note' }, 'fallback')).toBe('error wins');
    expect(errorMessageFromPayload({ note: 'note wins' }, 'fallback')).toBe('note wins');
    expect(errorMessageFromPayload({}, 'fallback')).toBe('fallback');
  });

  it('extracts probe error codes from direct fields and JSON output', () => {
    expect(probeErrorCodeFromPayload(response({ error: 'AUTH_FAILURE' }))).toBe('auth_failure');
    expect(probeErrorCodeFromPayload(response({ output: '{"error_code":"RATE_LIMIT"}' }))).toBe('rate_limit');
    expect(probeErrorCodeFromPayload(response({ output: '{"error":"timeout"}' }))).toBe('timeout');
    expect(probeErrorCodeFromPayload(response({ output: 'not-json' }))).toBe('');
  });

  it('preserves Codex account-home path and short display helpers', () => {
    const targets = [target('/tmp/codex-home/accounts/acct-a')];

    expect(codexAccountHomesRoot(targets)).toBe('/tmp/codex-home/accounts');
    expect(newCodexAccountHomePath(targets)).toMatch(/^\/tmp\/codex-home\/accounts\/acct-/);
    expect(codexAccountHomesRoot([])).toBe('/Users/shock/.mindscape/runtime/codex-home-pool/accounts');
    expect(shortRuntimeId('runtime-codex_cli-abc123')).toBe('codex:abc123');
    expect(shortKey('1234567890abcdef')).toBe('12345678...abcdef');
  });

  it('keeps source seams on one public auth UI path', () => {
    const sourceFiles = [
      '../CliApiKeysSection.tsx',
      './ApiKeyPane.tsx',
      './ModeSwitcher.tsx',
      './HostSessionPane.tsx',
      './useCodexAccountHomesController.ts',
      './useCliApiKeysSettingsController.ts',
      './codexAccountHomeHelpers.ts',
    ];
    const source = sourceFiles
      .map((relativePath) => readFileSync(new URL(relativePath, import.meta.url), 'utf8'))
      .join('\n');

    expect(source.match(/export default function CliApiKeysSection/g)).toHaveLength(1);
    expect(source.match(/setInterval/g)).toHaveLength(1);
    expect(source).toContain('}, 2000)');
    expect(source).toContain('}, 120000)');
    expect(source).toContain('CODEX_LOGIN_TIMEOUT_MS = 300_000');
    expect(source).toContain('CODEX_LOGOUT_TIMEOUT_MS = 45_000');
    expect(source).toContain('CODEX_PROBE_TIMEOUT_MS = 120_000');
    expect(source).toContain("from './cliApiKeys/GcaPoolPane'");

    for (const forbidden of [
      'APIRouter',
      'include_router',
      'PGBOUNCER_ADMIN_URL',
      'DB_POOL_SIZE',
      'create_engine(',
      'Queue(',
      'Thread(',
      'Process(',
    ]) {
      expect(source).not.toContain(forbidden);
    }
  });
});
