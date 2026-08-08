import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
    loader: 'tsx',
    include: /.*\.[jt]sx?$/,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
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
