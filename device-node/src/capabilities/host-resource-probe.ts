/**
 * Host Resource Probe Capability
 *
 * Provides a fixed, read-only host resource snapshot for Local-Core.
 * This intentionally avoids generic shell execution in admission paths.
 */

import { spawn } from "child_process";
import * as os from "os";

interface CommandResult {
    ok: boolean;
    command: string;
    args: string[];
    stdout: string;
    stderr: string;
    error?: string;
}

interface ParsedProcess {
    pid: number;
    ppid: number;
    cpu_percent: number;
    memory_percent: number;
    rss_kb: number;
    vsz_kb: number;
    command: string;
    args: string;
}

const DEFAULT_TIMEOUT_MS = 1000;
const PROCESS_MATCHER = /\b(mlx_vlm|mlx_lm|ollama|ComfyUI|comfyui|flux|qwen)\b/i;

function runFixedCommand(command: string, args: string[], timeoutMs: number): Promise<CommandResult> {
    return new Promise((resolve) => {
        let child;
        try {
            child = spawn(command, args, {
                shell: false,
                cwd: process.cwd(),
            });
        } catch (error) {
            resolve({
                ok: false,
                command,
                args,
                stdout: "",
                stderr: "",
                error: error instanceof Error ? error.message : String(error),
            });
            return;
        }
        let stdout = "";
        let stderr = "";
        let finished = false;
        const timer = setTimeout(() => {
            if (finished) {
                return;
            }
            finished = true;
            child.kill("SIGTERM");
            resolve({
                ok: false,
                command,
                args,
                stdout,
                stderr,
                error: `Timed out after ${timeoutMs}ms`,
            });
        }, timeoutMs);

        child.stdout.on("data", (chunk) => {
            stdout += chunk.toString();
        });
        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString();
        });
        child.on("error", (error) => {
            if (finished) {
                return;
            }
            finished = true;
            clearTimeout(timer);
            resolve({
                ok: false,
                command,
                args,
                stdout,
                stderr,
                error: error.message,
            });
        });
        child.on("close", (code, signal) => {
            if (finished) {
                return;
            }
            finished = true;
            clearTimeout(timer);
            resolve({
                ok: code === 0,
                command,
                args,
                stdout,
                stderr,
                error: code === 0 ? undefined : `Exited with code ${code}${signal ? ` signal ${signal}` : ""}`,
            });
        });
    });
}

function parseInteger(value: string | undefined): number | null {
    if (!value) {
        return null;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : null;
}

function parseFloatValue(value: string | undefined): number {
    if (!value) {
        return 0;
    }
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function parseMemoryPressure(raw: string): Record<string, number | null> {
    return {
        free_percent: parseInteger(raw.match(/System-wide memory free percentage:\s*(\d+)%/i)?.[1]),
        swapins: parseInteger(raw.match(/Swapins:\s*(\d+)/i)?.[1]),
        swapouts: parseInteger(raw.match(/Swapouts:\s*(\d+)/i)?.[1]),
    };
}

function normalizeVmStatKey(rawKey: string): string {
    return rawKey
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "");
}

function parseVmStat(raw: string): Record<string, number> {
    const parsed: Record<string, number> = {};
    for (const line of raw.split(/\r?\n/)) {
        const match = line.match(/^([^:]+):\s*([0-9]+)\.?/);
        if (!match) {
            continue;
        }
        const key = normalizeVmStatKey(match[1]);
        const value = Number.parseInt(match[2], 10);
        if (key && Number.isFinite(value)) {
            parsed[key] = value;
        }
    }
    return parsed;
}

function parseProcesses(raw: string): ParsedProcess[] {
    const processes: ParsedProcess[] = [];
    for (const line of raw.split(/\r?\n/).slice(1)) {
        const match = line.match(/^\s*(\d+)\s+(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/);
        if (!match) {
            continue;
        }
        const command = match[7] || "";
        const args = match[8] || "";
        if (!PROCESS_MATCHER.test(`${command} ${args}`)) {
            continue;
        }
        processes.push({
            pid: Number.parseInt(match[1], 10),
            ppid: Number.parseInt(match[2], 10),
            cpu_percent: parseFloatValue(match[3]),
            memory_percent: parseFloatValue(match[4]),
            rss_kb: Number.parseInt(match[5], 10),
            vsz_kb: Number.parseInt(match[6], 10),
            command,
            args,
        });
    }
    return processes;
}

function parseProcessIds(raw: string): string[] {
    const seen = new Set<string>();
    for (const line of raw.split(/\r?\n/)) {
        const match = line.match(/^\s*(\d+)\s+/);
        if (match) {
            seen.add(match[1]);
        }
    }
    return Array.from(seen).slice(0, 128);
}

function commandPayload(
    result: CommandResult,
    parsed?: unknown,
    options: { includeRaw?: boolean } = {}
): Record<string, unknown> {
    return {
        ok: result.ok,
        command: result.command,
        args: result.args,
        raw: options.includeRaw === false ? undefined : result.stdout,
        stderr: result.stderr,
        error: result.error,
        parsed,
    };
}

function processCommandPayload(result: CommandResult, parsed: ParsedProcess[]): Record<string, unknown> {
    return {
        ok: result.ok || parsed.length > 0,
        command: result.command,
        args: result.args,
        stderr: result.stderr,
        error: result.ok || parsed.length > 0 ? undefined : result.error,
        parsed,
    };
}

async function runProcessCensus(timeoutMs: number): Promise<Record<string, unknown>> {
    const processLookup = await runFixedCommand(
        "pgrep",
        ["-fil", "mlx_vlm|mlx_lm|ollama|ComfyUI|comfyui|flux|qwen"],
        timeoutMs
    );
    const processIds = parseProcessIds(processLookup.stdout);
    if (processIds.length === 0) {
        return processCommandPayload(processLookup, []);
    }
    const ps = await runFixedCommand(
        "ps",
        ["-p", processIds.join(","), "-o", "pid,ppid,pcpu,pmem,rss,vsz,comm,args"],
        timeoutMs
    );
    const matchingProcesses = parseProcesses(ps.stdout);
    return processCommandPayload(ps, matchingProcesses);
}

export async function hostResourceProbe(rawArgs: Record<string, unknown>): Promise<object> {
    const requestedTimeout =
        typeof rawArgs.timeout_ms === "number" && Number.isFinite(rawArgs.timeout_ms)
            ? Math.trunc(rawArgs.timeout_ms)
            : DEFAULT_TIMEOUT_MS;
    const timeoutMs = Math.min(Math.max(requestedTimeout, 250), 5000);

    const [memsize, ncpu, pressure, vmstat, processCensus] = await Promise.all([
        runFixedCommand("sysctl", ["-n", "hw.memsize"], timeoutMs),
        runFixedCommand("sysctl", ["-n", "hw.ncpu"], timeoutMs),
        runFixedCommand("memory_pressure", [], timeoutMs),
        runFixedCommand("vm_stat", [], timeoutMs),
        runProcessCensus(timeoutMs),
    ]);

    return {
        sampled_at: new Date().toISOString(),
        platform: process.platform,
        hostname: os.hostname(),
        host: {
            total_memory_bytes: parseInteger(memsize.stdout.trim()),
            cpu_count: parseInteger(ncpu.stdout.trim()),
            loadavg: os.loadavg(),
        },
        probes: {
            sysctl_hw_memsize: commandPayload(memsize),
            sysctl_hw_ncpu: commandPayload(ncpu),
            memory_pressure: commandPayload(pressure, parseMemoryPressure(pressure.stdout)),
            vm_stat: commandPayload(vmstat, parseVmStat(vmstat.stdout)),
            process_census: processCensus,
        },
    };
}
