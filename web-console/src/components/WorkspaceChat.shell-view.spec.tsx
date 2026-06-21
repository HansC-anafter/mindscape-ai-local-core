import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const workspaceRoot = process.cwd();
const componentDir = path.join(workspaceRoot, 'src/components');
const viewPath = path.join(componentDir, 'workspaceChat/WorkspaceChatContentView.tsx');
const wrapperPath = path.join(componentDir, 'WorkspaceChat.tsx');

describe('WorkspaceChat shell view seam', () => {
  it('keeps touched files below the line gate', () => {
    const files = [
      wrapperPath,
      path.join(componentDir, 'WorkspaceChat.shell-view.spec.tsx'),
      viewPath,
    ];

    for (const file of files) {
      const lineCount = readFileSync(file, 'utf8').split('\n').length;
      expect(lineCount, file).toBeLessThanOrEqual(500);
    }
  });

  it('keeps timer and window event ownership in the public wrapper', () => {
    const wrapperSource = readFileSync(wrapperPath, 'utf8');
    const viewSource = readFileSync(viewPath, 'utf8');

    expect(wrapperSource).toContain('window.dispatchEvent');
    expect(wrapperSource).toContain('setTimeout');
    expect(wrapperSource).toContain("import { WorkspaceChatContentView } from './workspaceChat/WorkspaceChatContentView'");
    expect(viewSource).not.toContain('setTimeout');
    expect(viewSource).not.toContain('window.');
    expect(viewSource).not.toContain('document.');
  });

  it('does not introduce raw fetch or polling markers in the wrapper or view seam', () => {
    const combinedSource = [
      readFileSync(wrapperPath, 'utf8'),
      readFileSync(viewPath, 'utf8'),
    ].join('\n');

    expect(combinedSource).not.toContain('fetch(');
    expect(combinedSource).not.toContain('setInterval');
    expect(combinedSource).not.toContain('EventSource');
    expect(combinedSource).not.toContain('WebSocket');
  });

  it('keeps default export provider shell and meeting sidebar dynamic import', () => {
    const wrapperSource = readFileSync(wrapperPath, 'utf8');

    expect(wrapperSource).toContain('export default function WorkspaceChat');
    expect(wrapperSource).toContain('<WorkspaceChatProvider');
    expect(wrapperSource).toContain("import('./workspace/WorkspaceChatMeetingSidebar')");
  });
});
