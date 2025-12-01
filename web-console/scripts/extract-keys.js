const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '../src/lib/i18n/locales');
const files = [
  'common',
  'app',
  'navigation',
  'mindscape',
  'playbooks',
  'profile',
  'intents',
  'timeline',
  'review',
  'habit',
  'majorProposal',
  'agents',
  'settings',
  'workbench',
  'system',
];

const keys = new Set();

files.forEach((file) => {
  const filePath = path.join(localesDir, `${file}.ts`);
  if (fs.existsSync(filePath)) {
    const content = fs.readFileSync(filePath, 'utf8');
    const matches = content.matchAll(/^\s+([a-zA-Z_][a-zA-Z0-9_]*):\s*['"`]/gm);
    for (const match of matches) {
      keys.add(match[1]);
    }
  }
});

const sortedKeys = Array.from(keys).sort();

console.log(`Total keys: ${sortedKeys.length}`);

const keysContent = `/**
 * Centralized i18n message keys
 * All message keys used across the application
 *
 * This file serves as the single source of truth for all i18n keys.
 * It enables type safety and LLM-based localization workflow.
 */

export const keys = {
${sortedKeys.map((key) => `  ${key}: true,`).join('\n')}
} as const;

export type MessageKey = keyof typeof keys;
`;

const outputPath = path.join(__dirname, '../src/lib/i18n/keys.ts');
fs.writeFileSync(outputPath, keysContent, 'utf8');

console.log(`Keys file generated: ${outputPath}`);
console.log(`Total keys: ${sortedKeys.length}`);
