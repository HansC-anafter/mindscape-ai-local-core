/**
 * Barrel re-export for WorkbenchExecutionPanel.
 *
 * The actual implementation is in the WorkbenchExecutionPanel/ directory (index.tsx).
 * This file exists so that existing imports like:
 *   import { WorkbenchExecutionPanel } from './workbench/components/WorkbenchExecutionPanel'
 * continue to resolve correctly (turbopack resolves .tsx files before directories).
 */
export { WorkbenchExecutionPanel, default } from './WorkbenchExecutionPanel/index';
