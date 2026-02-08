/**
 * Permission Map
 *
 * YAML-based permission governance for Device Node capabilities.
 * Defines trust levels and access rules for each capability.
 */

import * as fs from "fs";
import * as path from "path";
import { parse as parseYaml } from "yaml";
import { minimatch } from "minimatch";

export enum TrustLevel {
    READ = 1,
    DRAFT = 2,
    EXECUTE = 3,
    ADMIN = 4,
}

interface CapabilityPermission {
    trust_level: keyof typeof TrustLevel;
    confirm_required?: boolean;
    sandbox?: boolean;
    allowed_paths?: string[];
    denied_paths?: string[];
    allowed_commands?: string[];
    denied_commands?: string[];
}

interface PermissionConfig {
    version: string;
    trust_levels: Record<string, number>;
    capabilities: Record<string, CapabilityPermission>;
}

export interface PermissionCheckResult {
    allowed: boolean;
    reason?: string;
    requiresConfirmation: boolean;
    preview?: string;
}

export class PermissionMap {
    private configPath: string;
    private config: PermissionConfig | null = null;

    constructor(configPath: string) {
        this.configPath = configPath;
    }

    async load(): Promise<void> {
        if (!fs.existsSync(this.configPath)) {
            console.warn(`Permission config not found at ${this.configPath}, using defaults`);
            this.config = this.getDefaultConfig();
            return;
        }

        const content = fs.readFileSync(this.configPath, "utf-8");
        this.config = parseYaml(content) as PermissionConfig;
    }

    private getDefaultConfig(): PermissionConfig {
        return {
            version: "1.0",
            trust_levels: {
                read: 1,
                draft: 2,
                execute: 3,
                admin: 4,
            },
            capabilities: {
                filesystem_read: {
                    trust_level: "READ",
                    allowed_paths: ["~/Documents/**", "~/Projects/**", "~/**"],
                    denied_paths: ["~/.ssh/**", "~/.gnupg/**", "~/.aws/**"],
                },
                filesystem_write: {
                    trust_level: "DRAFT",
                    confirm_required: true,
                    allowed_paths: ["~/Documents/**", "~/Projects/**"],
                    denied_paths: ["~/.ssh/**", "~/.gnupg/**", "~/.aws/**", "/etc/**", "/usr/**"],
                },
                filesystem_list: {
                    trust_level: "READ",
                    allowed_paths: ["~/**"],
                    denied_paths: ["~/.ssh/**", "~/.gnupg/**"],
                },
                shell_execute: {
                    trust_level: "EXECUTE",
                    confirm_required: true,
                    allowed_commands: ["git", "npm", "node", "python", "ls", "cat", "echo", "pwd"],
                    denied_commands: ["rm -rf", "sudo", "chmod", "chown", "mkfs", "dd"],
                },
            },
        };
    }

    async checkPermission(
        capability: string,
        args: Record<string, unknown>
    ): Promise<PermissionCheckResult> {
        if (!this.config) {
            return { allowed: false, reason: "Permission map not loaded", requiresConfirmation: false };
        }

        const capConfig = this.config.capabilities[capability];
        if (!capConfig) {
            return { allowed: false, reason: `Unknown capability: ${capability}`, requiresConfirmation: false };
        }

        if (capability.startsWith("filesystem_")) {
            return this.checkFilesystemPermission(capConfig, args);
        }

        if (capability === "shell_execute") {
            return this.checkShellPermission(capConfig, args);
        }

        return {
            allowed: true,
            requiresConfirmation: capConfig.confirm_required ?? false,
        };
    }

    private checkFilesystemPermission(
        config: CapabilityPermission,
        args: Record<string, unknown>
    ): PermissionCheckResult {
        const filePath = args.path as string;
        if (!filePath) {
            return { allowed: false, reason: "Path is required", requiresConfirmation: false };
        }

        const expandedPath = this.expandPath(filePath);

        if (config.denied_paths) {
            for (const pattern of config.denied_paths) {
                if (minimatch(expandedPath, this.expandPath(pattern))) {
                    return {
                        allowed: false,
                        reason: `Path matches denied pattern: ${pattern}`,
                        requiresConfirmation: false,
                    };
                }
            }
        }

        if (config.allowed_paths) {
            let matched = false;
            for (const pattern of config.allowed_paths) {
                if (minimatch(expandedPath, this.expandPath(pattern))) {
                    matched = true;
                    break;
                }
            }
            if (!matched) {
                return {
                    allowed: false,
                    reason: "Path not in allowed paths",
                    requiresConfirmation: false,
                };
            }
        }

        return {
            allowed: true,
            requiresConfirmation: config.confirm_required ?? false,
            preview: `File operation on: ${filePath}`,
        };
    }

    private checkShellPermission(
        config: CapabilityPermission,
        args: Record<string, unknown>
    ): PermissionCheckResult {
        const command = args.command as string;
        if (!command) {
            return { allowed: false, reason: "Command is required", requiresConfirmation: false };
        }

        const baseCommand = command.split(" ")[0];

        if (config.denied_commands) {
            for (const denied of config.denied_commands) {
                if (command.includes(denied) || baseCommand === denied) {
                    return {
                        allowed: false,
                        reason: `Command is denied: ${denied}`,
                        requiresConfirmation: false,
                    };
                }
            }
        }

        if (config.allowed_commands) {
            if (!config.allowed_commands.includes(baseCommand)) {
                return {
                    allowed: false,
                    reason: `Command not in allowed list: ${baseCommand}`,
                    requiresConfirmation: false,
                };
            }
        }

        return {
            allowed: true,
            requiresConfirmation: config.confirm_required ?? true,
            preview: `Execute: ${command} ${(args.args as string[] || []).join(" ")}`,
        };
    }

    private expandPath(p: string): string {
        if (p.startsWith("~")) {
            return path.join(process.env.HOME || "/", p.slice(1));
        }
        return p;
    }
}
