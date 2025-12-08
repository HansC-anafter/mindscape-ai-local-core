/**
 * Centralized i18n message keys
 * All message keys used across the application
 *
 * This file serves as the single source of truth for all i18n keys.
 * It enables type safety and LLM-based localization workflow.
 *
 * NOTE: This file now re-exports from the modular keys/ directory.
 * The keys are organized by functional modules for better maintainability.
 */

export { keys, type MessageKey } from './keys/index';
