import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CloudPlaybookProvidersSettings } from './CloudPlaybookProvidersSettings';
import {
  buildCloudProviderFormFromProvider,
  buildCloudProviderPayload,
  markInstalledPacks,
} from './cloudPlaybookProvidersSettings/formState';
import { buildInstallDefaultPacksAcceptedMessage } from './cloudPlaybookProvidersSettings/installResult';
import { cloudPlaybookProviderSettingsEndpoints } from './cloudPlaybookProvidersSettings/resourceActions';
import type { Pack, Provider } from './cloudPlaybookProvidersSettings/types';

const notificationMock = vi.hoisted(() => ({
  showNotification: vi.fn(),
}));

vi.mock('../../hooks/useSettingsNotification', () => ({
  showNotification: notificationMock.showNotification,
}));

const panelsDir = dirname(fileURLToPath(import.meta.url));
const webConsoleRoot = join(panelsDir, '../../../..');
const touchedFiles = [
  'CloudPlaybookProvidersSettings.tsx',
  'CloudPlaybookProvidersSettings.spec.tsx',
  'cloudPlaybookProvidersSettings/CloudPlaybookProvidersSettingsView.tsx',
  'cloudPlaybookProvidersSettings/ProviderFormModal.tsx',
  'cloudPlaybookProvidersSettings/ProviderListSection.tsx',
  'cloudPlaybookProvidersSettings/ProviderPacksSection.tsx',
  'cloudPlaybookProvidersSettings/formState.ts',
  'cloudPlaybookProvidersSettings/installResult.ts',
  'cloudPlaybookProvidersSettings/resourceActions.ts',
  'cloudPlaybookProvidersSettings/types.ts',
];

function readPanelFile(pathFromPanels: string): string {
  return readFileSync(join(panelsDir, pathFromPanels), 'utf8');
}

function readWebConsoleFile(pathFromRoot: string): string {
  return readFileSync(join(webConsoleRoot, pathFromRoot), 'utf8');
}

function provider(overrides: Partial<Provider> = {}): Provider {
  return {
    provider_id: 'official',
    provider_type: 'generic_http',
    enabled: true,
    configured: true,
    name: 'Official Cloud',
    description: 'Official provider',
    config: {
      api_url: 'https://cloud.example.test',
      auth: {
        auth_type: 'bearer',
        token: 'masked',
      },
    },
    ...overrides,
  };
}

function pack(overrides: Partial<Pack> = {}): Pack {
  return {
    pack_ref: 'official:ig@1.0.0',
    code: 'ig',
    display_name: 'Instagram',
    version: '1.0.0',
    description: 'Instagram pack',
    bundle: 'default',
    size: 2048,
    ...overrides,
  };
}

describe('CloudPlaybookProvidersSettings seams', () => {
  beforeEach(() => {
    notificationMock.showNotification.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('queues install jobs without claiming completion or reloading packs immediately', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/v1/cloud-providers') {
        return {
          ok: true,
          json: async () => ([provider()]),
        } as Response;
      }

      if (url === '/api/v1/cloud-providers/official/packs') {
        return {
          ok: true,
          json: async () => ({
            packs: [pack()],
          }),
        } as Response;
      }

      if (url === '/api/v1/capability-packs') {
        return {
          ok: true,
          json: async () => ([]),
        } as Response;
      }

      if (url === '/api/v1/cloud-providers/official/install-default?bundle=default' && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            success: true,
            accepted: true,
            bundle: 'default',
            provider_id: 'official',
            jobs: [
              {
                pack_code: 'ig',
                pack_ref: 'official:ig@1.0.0',
                install_id: 'job-1',
                state: 'queued',
                status_url: '/api/v1/capability-packs/install-jobs/job-1',
              },
            ],
            skipped: [],
          }),
        } as Response;
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CloudPlaybookProvidersSettings />);

    fireEvent.click(await screen.findByRole('button', { name: 'View Packs' }));

    await screen.findByText('Instagram');
    fireEvent.click(screen.getByRole('button', { name: 'Install All Packs' }));

    await waitFor(() => {
      expect(notificationMock.showNotification).toHaveBeenCalledWith(
        'success',
        'Queued 1 pack install job: ig. Check install job status for completion.',
      );
    });

    const providerPacksCalls = fetchMock.mock.calls.filter(([url]) => (
      String(url) === '/api/v1/cloud-providers/official/packs'
    ));
    expect(providerPacksCalls).toHaveLength(1);

    const installedPackStatusCalls = fetchMock.mock.calls.filter(([url]) => (
      String(url) === '/api/v1/capability-packs'
    ));
    expect(installedPackStatusCalls).toHaveLength(1);

    const successMessages = notificationMock.showNotification.mock.calls
      .filter(([kind]) => kind === 'success')
      .map(([, message]) => String(message));
    expect(successMessages.some((message) => message.startsWith('Installed'))).toBe(false);
  });

  it('preserves endpoint and form payload shapes', () => {
    expect(cloudPlaybookProviderSettingsEndpoints.providers()).toBe('/api/v1/cloud-providers');
    expect(cloudPlaybookProviderSettingsEndpoints.provider('official')).toBe('/api/v1/cloud-providers/official');
    expect(cloudPlaybookProviderSettingsEndpoints.providerTest('official')).toBe('/api/v1/cloud-providers/official/test');
    expect(cloudPlaybookProviderSettingsEndpoints.providerPacks('official')).toBe('/api/v1/cloud-providers/official/packs');
    expect(cloudPlaybookProviderSettingsEndpoints.installedCapabilityPacks()).toBe('/api/v1/capability-packs');
    expect(cloudPlaybookProviderSettingsEndpoints.installDefaultPacks('official'))
      .toBe('/api/v1/cloud-providers/official/install-default?bundle=default');

    const form = buildCloudProviderFormFromProvider(provider({
      config: {
        api_url: 'https://cloud.example.test',
        name: 'Official Cloud',
        auth: {
          auth_type: 'api_key',
          api_key: 'masked-key',
        },
      },
    }));
    expect(form.config.auth.api_key).toBe('masked-key');
    expect(buildCloudProviderPayload(form)).toEqual({
      provider_id: 'official',
      provider_type: 'generic_http',
      enabled: true,
      config: {
        name: 'Official Cloud',
        api_url: 'https://cloud.example.test',
        auth: {
          auth_type: 'api_key',
          api_key: 'masked-key',
        },
      },
    });
  });

  it('marks installed packs by code or pack ref and formats accepted install results', () => {
    expect(markInstalledPacks([
      pack({ code: 'ig', pack_ref: 'official:ig@1.0.0' }),
      pack({ code: 'pd', pack_ref: 'official:performance_direction@1.0.0' }),
    ], [
      { id: 'performance_direction' },
    ])).toEqual([
      expect.objectContaining({ code: 'ig', installed: false }),
      expect.objectContaining({ code: 'pd', installed: true }),
    ]);

    expect(buildInstallDefaultPacksAcceptedMessage({
      success: true,
      accepted: true,
      jobs: [
        { pack_ref: 'official:ig@1.0.0', install_id: 'job-1', state: 'queued' },
      ],
    })).toBe('Queued 1 pack install job: ig. Check install job status for completion.');
    expect(buildInstallDefaultPacksAcceptedMessage({ accepted: true }))
      .toBe('Install request accepted. Check install job status for completion.');
  });

  it('keeps touched files below the line gate', () => {
    for (const fileName of touchedFiles) {
      const lineCount = readPanelFile(fileName).split(/\r?\n/).length;
      expect(lineCount, fileName).toBeLessThanOrEqual(500);
    }
  });

  it('keeps resource owners in the resource action seam only', () => {
    const wrapperSource = readPanelFile('CloudPlaybookProvidersSettings.tsx');
    expect(wrapperSource).toContain('export function CloudPlaybookProvidersSettings');
    expect(wrapperSource).not.toMatch(/\bfetch\s*\(/);
    expect(wrapperSource).not.toContain('AbortSignal');
    expect(wrapperSource).not.toContain('setInterval(');
    expect(wrapperSource).not.toContain('setTimeout(');

    const resourceSource = readPanelFile('cloudPlaybookProvidersSettings/resourceActions.ts');
    expect(resourceSource).toContain("installedCapabilityPacks: () => '/api/v1/capability-packs'");
    expect(resourceSource).toContain('AbortSignal.timeout(5000)');
    expect(resourceSource).toContain('fetch(');

    for (const fileName of [
      'cloudPlaybookProvidersSettings/CloudPlaybookProvidersSettingsView.tsx',
      'cloudPlaybookProvidersSettings/ProviderFormModal.tsx',
      'cloudPlaybookProvidersSettings/ProviderListSection.tsx',
      'cloudPlaybookProvidersSettings/ProviderPacksSection.tsx',
      'cloudPlaybookProvidersSettings/formState.ts',
      'cloudPlaybookProvidersSettings/installResult.ts',
    ]) {
      const source = readPanelFile(fileName);
      expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
      expect(source, fileName).not.toContain('AbortSignal');
      expect(source, fileName).not.toContain('setInterval(');
      expect(source, fileName).not.toContain('setTimeout(');
      expect(source, fileName).not.toContain('EventSource');
      expect(source, fileName).not.toContain('WebSocket');
      expect(source, fileName).not.toMatch(/\bworker\b/i);
      expect(source, fileName).not.toMatch(/\bqueue\b/i);
      expect(source, fileName).not.toMatch(/\bpgbouncer\b/i);
      expect(source, fileName).not.toMatch(/\bpostgres\b/i);
      expect(source, fileName).not.toMatch(/\bpool\b/i);
      expect(source, fileName).not.toMatch(/\bpoll/i);
    }
  });

  it('does not reroute the active cloud extension settings path', () => {
    const basicHost = readWebConsoleFile('app/settings/components/BasicSettingsSectionHost.tsx');
    const navigationRegistry = readWebConsoleFile('app/settings/navigation/settingsNavigationRegistry.ts');

    expect(basicHost).toContain("import('./panels/CloudExtensionSettings')");
    expect(basicHost).toContain('<CloudExtensionSettings />');
    expect(basicHost).not.toContain('CloudPlaybookProvidersSettings');
    expect(navigationRegistry).toContain("section: 'cloud-extension'");
  });

  it('keeps touched source files ascii only', () => {
    for (const fileName of touchedFiles) {
      expect(readPanelFile(fileName), fileName).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
