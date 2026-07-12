import fs from 'node:fs';
import path from 'node:path';

import {
  MAX_ARCHIVE_FILES,
  MAX_LOG_FILE_BYTES,
} from './constants.mjs';
import {
  archiveFilename,
} from './normalizers.mjs';

const STORAGE_ERROR_CODE = 'REMOTE_WORKBENCH_AUDIT_STORAGE_UNSAFE';
const DIRECTORY_MODE = 0o700;
const FILE_MODE = 0o600;

function unsafeStorage(reason) {
  const error = new Error(`Remote Workbench audit storage is unsafe: ${reason}`);
  error.code = STORAGE_ERROR_CODE;
  return error;
}

function requireNoFollowConstants() {
  const { O_DIRECTORY, O_NOFOLLOW } = fs.constants;
  if (!Number.isInteger(O_DIRECTORY) || !Number.isInteger(O_NOFOLLOW)) {
    throw unsafeStorage('no-follow filesystem operations are unavailable');
  }
  return { O_DIRECTORY, O_NOFOLLOW };
}

function assertDirectoryStats(stats) {
  if (!stats.isDirectory() || (stats.mode & 0o777) !== DIRECTORY_MODE) {
    throw unsafeStorage('base directory type or mode mismatch');
  }
}

function assertFileStats(stats) {
  if (!stats.isFile() || (stats.mode & 0o777) !== FILE_MODE) {
    throw unsafeStorage('audit file type or mode mismatch');
  }
}

async function verifyBaseDirectory(baseDir) {
  const { O_DIRECTORY, O_NOFOLLOW } = requireNoFollowConstants();
  let handle;
  try {
    handle = await fs.promises.open(
      baseDir,
      fs.constants.O_RDONLY | O_DIRECTORY | O_NOFOLLOW,
    );
    assertDirectoryStats(await handle.stat());
  } catch (error) {
    if (error?.code === STORAGE_ERROR_CODE) {
      throw error;
    }
    throw unsafeStorage('base directory is unavailable');
  } finally {
    await handle?.close();
  }
}

async function openExistingAuditFile(filePath, flags, { allowMissing = false } = {}) {
  const { O_NOFOLLOW } = requireNoFollowConstants();
  let handle;
  try {
    handle = await fs.promises.open(filePath, flags | O_NOFOLLOW);
    assertFileStats(await handle.stat());
    return handle;
  } catch (error) {
    await handle?.close();
    if (allowMissing && error?.code === 'ENOENT') {
      return null;
    }
    if (error?.code === STORAGE_ERROR_CODE) {
      throw error;
    }
    throw unsafeStorage('audit file is unavailable or unsafe');
  }
}

async function openActiveForAppend(activeLogPath) {
  const appendFlags = fs.constants.O_WRONLY | fs.constants.O_APPEND;
  const existing = await openExistingAuditFile(
    activeLogPath,
    appendFlags,
    { allowMissing: true },
  );
  if (existing) {
    return existing;
  }
  const { O_NOFOLLOW } = requireNoFollowConstants();
  let handle;
  try {
    handle = await fs.promises.open(
      activeLogPath,
      appendFlags | fs.constants.O_CREAT | fs.constants.O_EXCL | O_NOFOLLOW,
      FILE_MODE,
    );
    await handle.chmod(FILE_MODE);
    assertFileStats(await handle.stat());
    return handle;
  } catch (error) {
    await handle?.close();
    if (error?.code === 'EEXIST') {
      return openExistingAuditFile(activeLogPath, appendFlags);
    }
    if (error?.code === STORAGE_ERROR_CODE) {
      throw error;
    }
    throw unsafeStorage('active audit file could not be created safely');
  }
}

async function validateExistingAuditFiles(filePaths) {
  for (const filePath of filePaths) {
    const handle = await openExistingAuditFile(
      filePath,
      fs.constants.O_RDONLY,
      { allowMissing: true },
    );
    await handle?.close();
  }
}

async function secureUnlink(filePath) {
  const handle = await openExistingAuditFile(
    filePath,
    fs.constants.O_RDONLY,
    { allowMissing: true },
  );
  if (!handle) {
    return;
  }
  await handle.close();
  try {
    await fs.promises.unlink(filePath);
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      throw unsafeStorage('archive removal failed');
    }
  }
}

async function secureRename(sourcePath, targetPath) {
  const sourceHandle = await openExistingAuditFile(
    sourcePath,
    fs.constants.O_RDONLY,
    { allowMissing: true },
  );
  if (!sourceHandle) {
    return;
  }
  await sourceHandle.close();
  const targetHandle = await openExistingAuditFile(
    targetPath,
    fs.constants.O_RDONLY,
    { allowMissing: true },
  );
  await targetHandle?.close();
  try {
    await fs.promises.rename(sourcePath, targetPath);
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      throw unsafeStorage('archive rotation failed');
    }
  }
}

export function createRemoteWorkbenchLogStore({
  baseDir,
  activeLogPath,
}) {
  if (path.resolve(path.dirname(activeLogPath)) !== path.resolve(baseDir)) {
    throw unsafeStorage('active audit file is outside the managed directory');
  }
  let appendChain = Promise.resolve();
  let baseDirReadyPromise = null;
  const archivePaths = Array.from({ length: MAX_ARCHIVE_FILES }, (_, index) =>
    path.join(baseDir, archiveFilename(index + 1)));
  const managedPaths = [activeLogPath, ...archivePaths];

  function ensureBaseDir() {
    if (!baseDirReadyPromise) {
      baseDirReadyPromise = (async () => {
        try {
          await fs.promises.mkdir(baseDir, { recursive: true, mode: DIRECTORY_MODE });
        } catch {
          throw unsafeStorage('base directory could not be created safely');
        }
        await verifyBaseDirectory(baseDir);
        await validateExistingAuditFiles(managedPaths);
      })().catch((error) => {
        baseDirReadyPromise = null;
        throw error;
      });
    }
    return baseDirReadyPromise;
  }

  async function rotateLogsIfNeeded(nextWriteBytes = 0) {
    await ensureBaseDir();
    const activeHandle = await openExistingAuditFile(
      activeLogPath,
      fs.constants.O_RDONLY,
      { allowMissing: true },
    );
    const currentSize = activeHandle ? (await activeHandle.stat()).size : 0;
    await activeHandle?.close();
    if (currentSize + nextWriteBytes <= MAX_LOG_FILE_BYTES) {
      return;
    }
    await secureUnlink(archivePaths[MAX_ARCHIVE_FILES - 1]);
    for (let index = MAX_ARCHIVE_FILES - 1; index >= 1; index -= 1) {
      await secureRename(archivePaths[index - 1], archivePaths[index]);
    }
    await secureRename(activeLogPath, archivePaths[0]);
  }

  async function flushWrites() {
    try {
      await appendChain;
    } catch {
      // Reads still run their own secure validation after a failed append.
    }
  }

  function enqueueAppend(record) {
    const line = `${JSON.stringify(record)}\n`;
    const lineBytes = Buffer.byteLength(line);
    appendChain = appendChain
      .then(async () => {
        await rotateLogsIfNeeded(lineBytes);
        await verifyBaseDirectory(baseDir);
        const handle = await openActiveForAppend(activeLogPath);
        try {
          await handle.writeFile(line, { encoding: 'utf8' });
        } finally {
          await handle.close();
        }
      })
      .catch((error) => {
        console.error('[remote-workbench-observability] append failed', error);
      });
    return appendChain;
  }

  async function readRawRecords() {
    await ensureBaseDir();
    await flushWrites();
    await verifyBaseDirectory(baseDir);
    const records = [];
    for (const filePath of managedPaths) {
      const handle = await openExistingAuditFile(
        filePath,
        fs.constants.O_RDONLY,
        { allowMissing: true },
      );
      if (!handle) {
        continue;
      }
      let fileContents;
      try {
        fileContents = await handle.readFile({ encoding: 'utf8' });
      } finally {
        await handle.close();
      }
      const lines = fileContents.split('\n').filter(Boolean);
      for (const line of lines) {
        try {
          const record = JSON.parse(line);
          if (record && typeof record === 'object') {
            records.push(record);
          }
        } catch {
          // Skip malformed lines and preserve read availability.
        }
      }
    }
    return records;
  }

  return {
    enqueueAppend,
    readRawRecords,
  };
}
