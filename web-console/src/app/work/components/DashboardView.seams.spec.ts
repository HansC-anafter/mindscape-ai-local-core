import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const componentDir = dirname(fileURLToPath(import.meta.url));
const workAppDir = resolve(componentDir, '..');
const touchedFiles = [
    'DashboardView.tsx',
    'dashboardViewTypes.ts',
    'dashboardViewPanels.tsx',
    'dashboardViewLists.tsx',
    'DashboardView.seams.spec.ts',
];
const implementationFiles = touchedFiles.filter((fileName) => fileName !== 'DashboardView.seams.spec.ts');

function readComponentFile(fileName: string): string {
    return readFileSync(join(componentDir, fileName), 'utf8');
}

function readWorkFile(relativePath: string): string {
    return readFileSync(join(workAppDir, relativePath), 'utf8');
}

describe('DashboardView seams', () => {
    it('keeps touched dashboard files below the line gate', () => {
        for (const fileName of touchedFiles) {
            const lineCount = readComponentFile(fileName).split(/\r?\n/).length;
            expect(lineCount, fileName).toBeLessThanOrEqual(500);
        }
    });

    it('keeps DashboardView as the public dashboard shell used by WorkspaceLayout', () => {
        const shell = readComponentFile('DashboardView.tsx');
        const workspaceLayout = readComponentFile('WorkspaceLayout.tsx');

        expect(shell).toContain('export function DashboardView()');
        expect(shell).toContain("from './dashboardViewPanels'");
        expect(shell).toContain("from './dashboardViewLists'");
        expect(shell).toContain("from './dashboardViewTypes'");
        expect(workspaceLayout).toContain("import { DashboardView } from './DashboardView'");
        expect(workspaceLayout).toContain("<DashboardView />");
    });

    it('keeps retired Chat Capture source-copy UI out of WorkspaceLayout', () => {
        const workspaceLayout = readComponentFile('WorkspaceLayout.tsx');

        expect(workspaceLayout).not.toContain('chat_capture');
        expect(workspaceLayout).not.toContain('chat-capture');
        expect(workspaceLayout).not.toContain('ChatCaptureWorkbench');
        expect(workspaceLayout).not.toContain('/api/v1/chat-capture');
    });

    it('keeps raw dashboard API ownership in existing hooks', () => {
        const dashboardHook = readWorkFile('hooks/useDashboard.ts');
        const savedViewsHook = readWorkFile('hooks/useSavedViews.ts');

        expect(dashboardHook).toContain('/api/v1/dashboard/summary');
        expect(dashboardHook).toContain('/api/v1/dashboard/inbox');
        expect(savedViewsHook).toContain('/api/v1/dashboard/saved-views');
    });

    it('keeps touched view seams free of raw resource owners', () => {
        for (const fileName of implementationFiles) {
            const source = readComponentFile(fileName);
            expect(source, fileName).not.toMatch(/\bfetch\s*\(/);
            expect(source, fileName).not.toContain('/api/v1/');
            expect(source, fileName).not.toContain('setInterval');
            expect(source, fileName).not.toContain('setTimeout');
            expect(source, fileName).not.toContain('WebSocket');
            expect(source, fileName).not.toContain('EventSource');
            expect(source, fileName).not.toContain('localStorage');
            expect(source, fileName).not.toContain('sessionStorage');
            expect(source, fileName).not.toContain('router.push');
            expect(source, fileName).not.toContain('window.location');
        }
    });
});
