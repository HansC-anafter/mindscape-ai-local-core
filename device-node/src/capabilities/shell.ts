/**
 * Shell Capability
 *
 * Provides limited shell command execution with:
 * - argv-based execution (no shell injection)
 * - Command whitelist with subcommand/flag restrictions
 */

import { spawn } from "child_process";

interface CommandRule {
    allowed_subcommands?: string[];
    denied_flags?: string[];
}

type CommandWhitelist = Record<string, CommandRule>;

interface ShellArgs {
    command: string;
    subcommand?: string;
    args?: string[];
    cwd?: string;
    _commandWhitelist?: CommandWhitelist;
}

const DEFAULT_WHITELIST: CommandWhitelist = {
    git: {
        allowed_subcommands: ["status", "log", "diff", "branch", "checkout", "pull", "push", "add", "commit", "stash", "fetch"],
        denied_flags: ["--force", "-f", "--hard"],
    },
    npm: {
        allowed_subcommands: ["install", "run", "test", "build", "start", "ci", "audit"],
        denied_flags: ["--unsafe-perm"],
    },
    node: {
        allowed_subcommands: [],
        denied_flags: ["--eval", "-e"],
    },
    python: {
        allowed_subcommands: [],
        denied_flags: ["-c", "--command"],
    },
    python3: {
        allowed_subcommands: [],
        denied_flags: ["-c", "--command"],
    },
    ls: { allowed_subcommands: [], denied_flags: [] },
    cat: { allowed_subcommands: [], denied_flags: [] },
    echo: { allowed_subcommands: [], denied_flags: [] },
    pwd: { allowed_subcommands: [], denied_flags: [] },
    mkdir: { allowed_subcommands: [], denied_flags: [] },
    touch: { allowed_subcommands: [], denied_flags: [] },
};

function validateCommand(
    args: ShellArgs,
    whitelist: CommandWhitelist
): { valid: boolean; reason?: string } {
    const rule = whitelist[args.command];

    if (!rule) {
        return { valid: false, reason: `Command not in whitelist: ${args.command}` };
    }

    if (rule.allowed_subcommands && rule.allowed_subcommands.length > 0) {
        if (!args.subcommand) {
            return { valid: false, reason: `Subcommand required for ${args.command}` };
        }
        if (!rule.allowed_subcommands.includes(args.subcommand)) {
            return { valid: false, reason: `Subcommand not allowed: ${args.command} ${args.subcommand}` };
        }
    }

    if (rule.denied_flags && args.args) {
        for (const arg of args.args) {
            for (const denied of rule.denied_flags) {
                if (arg === denied || arg.startsWith(`${denied}=`)) {
                    return { valid: false, reason: `Flag not allowed: ${denied}` };
                }
            }
        }
    }

    return { valid: true };
}

export async function shellExecute(
    rawArgs: Record<string, unknown>
): Promise<string> {
    const args: ShellArgs = {
        command: rawArgs.command as string,
        subcommand: rawArgs.subcommand as string | undefined,
        args: rawArgs.args as string[] | undefined,
        cwd: rawArgs.cwd as string | undefined,
        _commandWhitelist: rawArgs._commandWhitelist as CommandWhitelist | undefined,
    };

    const whitelist = args._commandWhitelist || DEFAULT_WHITELIST;
    const validation = validateCommand(args, whitelist);

    if (!validation.valid) {
        throw new Error(`Permission denied: ${validation.reason}`);
    }

    const cmdArgs: string[] = [];
    if (args.subcommand) {
        cmdArgs.push(args.subcommand);
    }
    if (args.args) {
        cmdArgs.push(...args.args);
    }

    return new Promise((resolve, reject) => {
        const child = spawn(args.command, cmdArgs, {
            cwd: args.cwd || process.cwd(),
            shell: false,
            timeout: 30000,
        });

        let stdout = "";
        let stderr = "";

        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });

        child.stderr.on("data", (data) => {
            stderr += data.toString();
        });

        child.on("close", (code) => {
            if (code === 0) {
                resolve(stdout || "(no output)");
            } else {
                reject(new Error(`Command exited with code ${code}: ${stderr || stdout}`));
            }
        });

        child.on("error", (error) => {
            reject(new Error(`Failed to execute command: ${error.message}`));
        });
    });
}
