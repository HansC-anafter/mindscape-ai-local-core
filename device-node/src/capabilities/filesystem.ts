/**
 * Filesystem Capability
 *
 * Provides sandboxed filesystem access with:
 * - realpath validation (prevents symlink escape)
 * - Path-based permission checks
 */

import * as fs from "fs/promises";
import * as path from "path";

interface PathValidation {
    valid: boolean;
    realPath: string;
    reason?: string;
}

/**
 * Validate path with realpath resolution to prevent symlink attacks.
 * Uses realpath to resolve symlinks before permission check.
 */
export async function validatePath(
    inputPath: string,
    allowedPaths: string[],
    deniedPaths: string[]
): Promise<PathValidation> {
    const expandedPath = expandPath(inputPath);

    let realPath: string;
    try {
        realPath = await fs.realpath(expandedPath);
    } catch {
        const parent = path.dirname(expandedPath);
        try {
            const parentReal = await fs.realpath(parent);
            realPath = path.join(parentReal, path.basename(expandedPath));
        } catch {
            realPath = expandedPath;
        }
    }

    for (const pattern of deniedPaths) {
        const expandedPattern = expandPath(pattern).replace(/\/\*\*$/, "");
        if (realPath.startsWith(expandedPattern) || realPath === expandedPattern) {
            return { valid: false, realPath, reason: `Path denied: ${pattern}` };
        }
    }

    let allowed = false;
    for (const pattern of allowedPaths) {
        const expandedPattern = expandPath(pattern).replace(/\/\*\*$/, "");
        if (realPath.startsWith(expandedPattern) || realPath === expandedPattern) {
            allowed = true;
            break;
        }
    }

    if (!allowed) {
        return { valid: false, realPath, reason: "Path not in allowed list" };
    }

    return { valid: true, realPath };
}

export async function filesystemRead(
    args: Record<string, unknown>
): Promise<string> {
    const filePath = args.path as string;
    const allowedPaths = (args._allowedPaths as string[]) || ["~/**"];
    const deniedPaths = (args._deniedPaths as string[]) || [];

    const validation = await validatePath(filePath, allowedPaths, deniedPaths);
    if (!validation.valid) {
        throw new Error(`Permission denied: ${validation.reason}`);
    }

    try {
        const content = await fs.readFile(validation.realPath, "utf-8");
        return content;
    } catch (error) {
        if (error instanceof Error && "code" in error) {
            if ((error as NodeJS.ErrnoException).code === "ENOENT") {
                throw new Error(`File not found: ${validation.realPath}`);
            }
            if ((error as NodeJS.ErrnoException).code === "EACCES") {
                throw new Error(`System permission denied: ${validation.realPath}`);
            }
        }
        throw error;
    }
}

export async function filesystemWrite(
    args: Record<string, unknown>
): Promise<string> {
    const filePath = args.path as string;
    const content = args.content as string;
    const allowedPaths = (args._allowedPaths as string[]) || [];
    const deniedPaths = (args._deniedPaths as string[]) || [];

    const validation = await validatePath(filePath, allowedPaths, deniedPaths);
    if (!validation.valid) {
        throw new Error(`Permission denied: ${validation.reason}`);
    }

    try {
        const dir = path.dirname(validation.realPath);
        await fs.mkdir(dir, { recursive: true });
        await fs.writeFile(validation.realPath, content, "utf-8");
        return `Successfully wrote ${content.length} bytes to ${validation.realPath}`;
    } catch (error) {
        if (error instanceof Error && "code" in error) {
            if ((error as NodeJS.ErrnoException).code === "EACCES") {
                throw new Error(`System permission denied: ${validation.realPath}`);
            }
        }
        throw error;
    }
}

export async function filesystemList(
    args: Record<string, unknown>
): Promise<object[]> {
    const dirPath = args.path as string;
    const allowedPaths = (args._allowedPaths as string[]) || ["~/**"];
    const deniedPaths = (args._deniedPaths as string[]) || [];

    const validation = await validatePath(dirPath, allowedPaths, deniedPaths);
    if (!validation.valid) {
        throw new Error(`Permission denied: ${validation.reason}`);
    }

    try {
        const entries = await fs.readdir(validation.realPath, { withFileTypes: true });

        const result = await Promise.all(
            entries.map(async (entry) => {
                const fullPath = path.join(validation.realPath, entry.name);
                try {
                    const stats = await fs.stat(fullPath);
                    return {
                        name: entry.name,
                        type: entry.isDirectory() ? "directory" : "file",
                        size: stats.size,
                        modified: stats.mtime.toISOString(),
                    };
                } catch {
                    return {
                        name: entry.name,
                        type: entry.isDirectory() ? "directory" : "file",
                        size: 0,
                        modified: null,
                    };
                }
            })
        );

        return result;
    } catch (error) {
        if (error instanceof Error && "code" in error) {
            if ((error as NodeJS.ErrnoException).code === "ENOENT") {
                throw new Error(`Directory not found: ${validation.realPath}`);
            }
            if ((error as NodeJS.ErrnoException).code === "EACCES") {
                throw new Error(`System permission denied: ${validation.realPath}`);
            }
        }
        throw error;
    }
}

function expandPath(p: string): string {
    if (p.startsWith("~")) {
        return path.join(process.env.HOME || "/", p.slice(1));
    }
    if (!path.isAbsolute(p)) {
        return path.resolve(process.cwd(), p);
    }
    return p;
}
