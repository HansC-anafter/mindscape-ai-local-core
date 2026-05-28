import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/dist/',
        '**/build/',
      ],
    },
  },
  resolve: {
    alias: [
      {
        find: '@',
        replacement: path.resolve(__dirname, './src'),
      },
      {
        find: 'roughjs/bin/rough',
        replacement: path.resolve(__dirname, './node_modules/roughjs/bin/rough.js'),
      },
      {
        find: '@excalidraw/excalidraw',
        replacement: path.resolve(__dirname, './src/test/mocks/excalidraw.tsx'),
      },
      {
        find: '@excalidraw/excalidraw/index.css',
        replacement: path.resolve(__dirname, './src/test/mocks/styleMock.ts'),
      },
      {
        find: 'reactflow/dist/style.css',
        replacement: path.resolve(__dirname, './src/test/mocks/styleMock.ts'),
      },
      {
        find: 'reactflow',
        replacement: path.resolve(__dirname, './src/test/mocks/reactflow.tsx'),
      },
      {
        find: /DepartmentWorkspaceExcalidrawClient$/,
        replacement: path.resolve(__dirname, './src/test/mocks/departmentWorkspaceExcalidrawClient.tsx'),
      },
    ],
  },
});
