import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_OBSERVABILITY_DIR = path.resolve(
  MODULE_DIR,
  '../../../data/host-services/mobile-workbench-gateway',
);
export const ACTIVE_LOG_FILENAME = 'access.current.ndjson';
export const MAX_ARCHIVE_FILES = 4;
export const MAX_LOG_FILE_BYTES = 2 * 1024 * 1024;
export const DEFAULT_SUMMARY_WINDOW_MS = 60 * 60 * 1000;
export const DEFAULT_AUDIT_LIMIT = 40;
export const MAX_AUDIT_LIMIT = 200;
export const LATENCY_BUCKETS = [
  { label: '<=250ms', upper_bound_ms: 250 },
  { label: '251-1000ms', upper_bound_ms: 1000 },
  { label: '1001-5000ms', upper_bound_ms: 5000 },
  { label: '5001-15000ms', upper_bound_ms: 15000 },
  { label: '>15000ms', upper_bound_ms: null },
];
