import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  SettingsAssistantHttpError,
  buildSettingsAssistantChatPayload,
  buildSettingsAssistantChatUrl,
  isSettingsAssistantUnavailableError,
  sendSettingsAssistantChat,
} from './settingsConfigAssistantApi';

const routeDir = dirname(fileURLToPath(import.meta.url));
const touchedFiles = [
  'SettingsConfigAssistant.tsx',
  'settingsConfigAssistantApi.ts',
  'settingsConfigAssistantApi.spec.ts',
];

function readRouteFile(fileName: string): string {
  return readFileSync(join(routeDir, fileName), 'utf8');
}

function jsonResponse(data: unknown, ok = true, status = ok ? 200 : 500) {
  return Promise.resolve({
    ok,
    status,
    json: () => Promise.resolve(data),
  } as Response);
}

describe('settings config assistant API seam', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the existing assistant chat endpoint', () => {
    expect(buildSettingsAssistantChatUrl('')).toBe('/api/v1/system-settings/assistant/chat');
    expect(buildSettingsAssistantChatUrl('http://api.test')).toBe(
      'http://api.test/api/v1/system-settings/assistant/chat'
    );
  });

  it('builds the preserved assistant chat payload shape', () => {
    expect(buildSettingsAssistantChatPayload({
      message: 'Help configure models',
      currentTab: 'basic',
      currentSection: 'llm-api-keys',
      configSnapshot: { backend: { mode: 'local' } },
      systemPrompt: 'System prompt',
    })).toEqual({
      message: 'Help configure models',
      context: {
        current_tab: 'basic',
        current_section: 'llm-api-keys',
        config_snapshot: { backend: { mode: 'local' } },
      },
      system_prompt: 'System prompt',
    });
  });

  it('posts assistant chat requests through the single API owner', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) => jsonResponse({
      response: 'Use the basic settings panel.',
      actions: [{ label: 'Basic Settings', action: 'navigate', params: { tab: 'basic' } }],
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(sendSettingsAssistantChat({
      message: 'Help configure models',
      currentTab: 'basic',
      currentSection: 'llm-api-keys',
      configSnapshot: { backend: { mode: 'local' } },
      systemPrompt: 'System prompt',
    }, 'http://api.test')).resolves.toEqual({
      response: 'Use the basic settings panel.',
      actions: [{ label: 'Basic Settings', action: 'navigate', params: { tab: 'basic' } }],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/system-settings/assistant/chat',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(requestInit.body))).toMatchObject({
      message: 'Help configure models',
      context: {
        current_tab: 'basic',
        current_section: 'llm-api-keys',
      },
      system_prompt: 'System prompt',
    });
  });

  it('classifies unavailable assistant statuses for the manual-send fallback', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ detail: 'missing' }, false, 501)));

    await expect(sendSettingsAssistantChat({
      message: 'Help',
      currentTab: 'basic',
      systemPrompt: 'System prompt',
    }, '')).rejects.toMatchObject({ status: 501 });

    expect(isSettingsAssistantUnavailableError(new SettingsAssistantHttpError(404))).toBe(true);
    expect(isSettingsAssistantUnavailableError(new SettingsAssistantHttpError(501))).toBe(true);
    expect(isSettingsAssistantUnavailableError(new SettingsAssistantHttpError(500))).toBe(false);
  });

  it('keeps touched settings assistant files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readRouteFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps raw fetch ownership in the API seam only', () => {
    const componentSource = readRouteFile('SettingsConfigAssistant.tsx');
    const apiSource = readRouteFile('settingsConfigAssistantApi.ts');

    expect(componentSource).not.toMatch(/\bfetch\s*\(/);
    expect(apiSource).toMatch(/\bfetch\s*\(/);
    for (const fileName of ['SettingsConfigAssistant.tsx', 'settingsConfigAssistantApi.ts']) {
      const source = readRouteFile(fileName);
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('localStorage');
      expect(source, fileName).not.toContain('sessionStorage');
    }
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readRouteFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
