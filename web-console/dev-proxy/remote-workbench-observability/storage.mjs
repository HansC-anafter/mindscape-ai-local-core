import fs from 'node:fs';
import path from 'node:path';

import {
  MAX_ARCHIVE_FILES,
  MAX_LOG_FILE_BYTES,
} from './constants.mjs';
import {
  archiveFilename,
} from './normalizers.mjs';

async function safeUnlink(filePath) {
  try {
    await fs.promises.rm(filePath, { force: true });
  } catch {
    // Best-effort cleanup only.
  }
}

async function safeRename(sourcePath, targetPath) {
  try {
    await fs.promises.rename(sourcePath, targetPath);
  } catch (error) {
    if (error?.code !== 'ENOENT') {
      throw error;
    }
  }
}

export function createRemoteWorkbenchLogStore({
  baseDir,
  activeLogPath,
}) {
  let appendChain = Promise.resolve();

  async function ensureBaseDir() {
    await fs.promises.mkdir(baseDir, { recursive: true });
  }

  async function rotateLogsIfNeeded(nextWriteBytes = 0) {
    await ensureBaseDir();
    let currentSize = 0;
    try {
      const stats = await fs.promises.stat(activeLogPath);
      currentSize = stats.size;
    } catch (error) {
      if (error?.code !== 'ENOENT') {
        throw error;
      }
    }
    if (currentSize + nextWriteBytes <= MAX_LOG_FILE_BYTES) {
      return;
    }
    await safeUnlink(path.join(baseDir, archiveFilename(MAX_ARCHIVE_FILES)));
    for (let index = MAX_ARCHIVE_FILES - 1; index >= 1; index -= 1) {
      await safeRename(
        path.join(baseDir, archiveFilename(index)),
        path.join(baseDir, archiveFilename(index + 1)),
      );
    }
    await safeRename(activeLogPath, path.join(baseDir, archiveFilename(1)));
  }

  async function flushWrites() {
    try {
      await appendChain;
    } catch {
      // Reads should stay available even when a prior append failed.
    }
  }

  function enqueueAppend(record) {
    const line = `${JSON.stringify(record)}\n`;
    const lineBytes = Buffer.byteLength(line);
    appendChain = appendChain
      .then(async () => {
        await rotateLogsIfNeeded(lineBytes);
        await ensureBaseDir();
        await fs.promises.appendFile(activeLogPath, line, 'utf8');
      })
      .catch((error) => {
        console.error('[remote-workbench-observability] append failed', error);
      });
    return appendChain;
  }

  async function readRawRecords() {
    await flushWrites();
    const candidateFiles = [
      activeLogPath,
      ...Array.from({ length: MAX_ARCHIVE_FILES }, (_, index) =>
        path.join(baseDir, archiveFilename(index + 1))),
    ];
    const records = [];
    for (const filePath of candidateFiles) {
      let fileContents = '';
      try {
        fileContents = await fs.promises.readFile(filePath, 'utf8');
      } catch (error) {
        if (error?.code === 'ENOENT') {
          continue;
        }
        throw error;
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
