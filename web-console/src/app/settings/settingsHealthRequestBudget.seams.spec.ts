import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const settingsDir = dirname(fileURLToPath(import.meta.url));

function read(relativePath: string): string {
  return readFileSync(join(settingsDir, relativePath), 'utf8');
}

describe('Settings deep-health request budget', () => {
  it('keeps the assistant shell free of deep health and timer polling', () => {
    const source = read('hooks/useSettingsContext.ts');

    expect(source).not.toContain("'/health'");
    expect(source).not.toContain('/health`');
    expect(source).not.toContain('setInterval');
    expect(source).toContain("vector_db: 'unknown'");
  });

  it('derives vector status from the one vector config request', () => {
    const source = read('hooks/useTools.ts');

    expect(source).toContain("'/api/v1/vector-db/config'");
    expect(source).toContain('data.adapter_available === true');
    expect(source).toContain('loadVectorDBConfig();');
    expect(source).not.toContain('loadVectorDBHealthStatus');
    expect(source).not.toContain('/health');
  });

  it('keeps ToolsPanel free of a duplicate health request', () => {
    const source = read('components/ToolsPanel.tsx');

    expect(source).not.toContain('/health');
    expect(source).toContain('useEffect(() => {\n    loadTools();\n    loadToolsStatus();');
    expect(source).not.toContain('loadTools();\n    loadVectorDBConfig();\n    loadToolsStatus();');
  });

  it('limits deep polling to visible explicit diagnostics with no retry', () => {
    const source = read('components/ServiceStatusPanel.tsx');

    expect(source).toContain('sharedGetFetch');
    expect(source).toContain("dedupKey: requestKey, maxAttempts: 1");
    expect(source).toContain('document.hidden');
    expect(source).toContain("visibilitychange");
    expect(source).toContain('activeRequestRef.current?.controller.abort()');
    expect(source.match(/setInterval/g)).toHaveLength(1);
    expect(source).toContain('30000');
  });
});
