import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import type { HostRuntimeDesired } from "./host-runtime-supervisor.js";

export function verifyHostRuntimeInventory(
    value: unknown,
    desired: HostRuntimeDesired,
    root: string,
): Map<string, { sha256: string }> {
    const inventory = requireRecord(value, "host_runtime_inventory_invalid");
    requireExactKeys(
        inventory,
        [
            "schema_version",
            "capability_code",
            "capability_version",
            "requirements",
            "assets",
            "tree_sha256",
        ],
        "host_runtime_inventory_keys_invalid",
    );
    if (
        inventory.schema_version !== "mindscape.capability-host-assets.v1"
        || inventory.capability_code !== desired.capabilityCode
        || inventory.capability_version !== desired.capabilityVersion
    ) {
        throw new Error("host_runtime_inventory_identity_mismatch");
    }
    const unsigned = { ...inventory };
    delete unsigned.tree_sha256;
    const treeDigest = crypto
        .createHash("sha256")
        .update(canonicalJson(unsigned))
        .digest("hex");
    if (treeDigest !== desired.hostAssetsDigest || inventory.tree_sha256 !== treeDigest) {
        throw new Error("host_runtime_inventory_digest_mismatch");
    }
    if (
        !Array.isArray(inventory.assets)
        || inventory.assets.length === 0
        || inventory.assets.length > 128
    ) {
        throw new Error("host_runtime_inventory_assets_invalid");
    }
    verifyRequirement(inventory.requirements, desired);
    const result = new Map<string, { sha256: string }>();
    for (const rawAsset of inventory.assets) {
        const asset = requireRecord(rawAsset, "host_runtime_asset_invalid");
        requireExactKeys(
            asset,
            ["path", "sha256", "size_bytes", "mode"],
            "host_runtime_asset_keys_invalid",
        );
        if (
            typeof asset.path !== "string"
            || path.posix.isAbsolute(asset.path)
            || asset.path.split("/").includes("..")
            || typeof asset.sha256 !== "string"
            || !/^[0-9a-f]{64}$/.test(asset.sha256)
            || !Number.isInteger(asset.size_bytes)
            || typeof asset.mode !== "string"
            || !/^(0600|0640|0644|0700|0750|0755)$/.test(asset.mode)
            || result.has(asset.path)
        ) {
            throw new Error("host_runtime_asset_identity_invalid");
        }
        const assetPath = path.join(root, ...asset.path.split("/"));
        const assetStat = fs.lstatSync(assetPath);
        if (!assetStat.isFile() || assetStat.isSymbolicLink()) {
            throw new Error("host_runtime_asset_type_mismatch");
        }
        if (fs.realpathSync(assetPath) !== assetPath) {
            throw new Error("host_runtime_asset_redirected");
        }
        const bytes = fs.readFileSync(assetPath);
        if (
            bytes.byteLength !== asset.size_bytes
            || crypto.createHash("sha256").update(bytes).digest("hex") !== asset.sha256
            || (assetStat.mode & 0o777).toString(8).padStart(4, "0") !== asset.mode
        ) {
            throw new Error("host_runtime_asset_identity_mismatch");
        }
        result.set(asset.path, { sha256: asset.sha256 });
    }
    const expectedPaths = new Set([...result.keys(), "host_assets.json"]);
    const actualPaths = collectTreeFiles(root);
    if (
        actualPaths.size !== expectedPaths.size
        || [...actualPaths].some((assetPath) => !expectedPaths.has(assetPath))
    ) {
        throw new Error("host_runtime_installed_tree_mismatch");
    }
    return result;
}

function verifyRequirement(value: unknown, desired: HostRuntimeDesired): void {
    if (!Array.isArray(value) || value.length === 0) {
        throw new Error("host_runtime_requirements_invalid");
    }
    const requirement = value.find(
        (candidate) => (
            candidate !== null
            && typeof candidate === "object"
            && !Array.isArray(candidate)
            && (candidate as Record<string, unknown>).requirement_code
            === desired.requirementCode
        ),
    );
    const record = requireRecord(requirement, "host_runtime_requirement_missing");
    requireExactKeys(
        record,
        [
            "requirement_code",
            "entrypoint",
            "operations",
            "permission_classes",
            "resource_lane",
            "share_policy",
            "runtime_assets",
        ],
        "host_runtime_requirement_keys_invalid",
    );
    if (
        record.entrypoint !== desired.entrypoint
        || record.resource_lane !== desired.resourceLane
        || !Array.isArray(record.operations)
        || !record.operations.includes(desired.operation)
        || (
            desired.declaredOperations !== undefined
            && JSON.stringify(record.operations)
            !== JSON.stringify(desired.declaredOperations)
        )
        || !Array.isArray(record.permission_classes)
        || JSON.stringify(record.permission_classes)
        !== JSON.stringify(desired.permissionClasses)
        || !Array.isArray(record.runtime_assets)
        || !record.runtime_assets.includes(desired.entrypoint)
    ) {
        throw new Error("host_runtime_requirement_identity_mismatch");
    }
}

function collectTreeFiles(root: string): Set<string> {
    const files = new Set<string>();
    const visit = (directory: string): void => {
        for (const name of fs.readdirSync(directory)) {
            const candidate = path.join(directory, name);
            const candidateStat = fs.lstatSync(candidate);
            if (candidateStat.isSymbolicLink()) {
                throw new Error("host_runtime_installed_tree_redirected");
            }
            if (candidateStat.isDirectory()) {
                visit(candidate);
            } else if (candidateStat.isFile()) {
                files.add(path.relative(root, candidate).split(path.sep).join("/"));
            } else {
                throw new Error("host_runtime_installed_tree_type_invalid");
            }
        }
    };
    visit(root);
    return files;
}

export function canonicalJson(value: unknown): string {
    if (Array.isArray(value)) {
        return `[${value.map(canonicalJson).join(",")}]`;
    }
    if (value !== null && typeof value === "object") {
        const record = value as Record<string, unknown>;
        return `{${Object.keys(record).sort().map(
            (key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`,
        ).join(",")}}`;
    }
    return JSON.stringify(value);
}

function requireRecord(value: unknown, code: string): Record<string, unknown> {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(code);
    }
    return value as Record<string, unknown>;
}

function requireExactKeys(
    value: Record<string, unknown>,
    expected: string[],
    code: string,
): void {
    const actual = Object.keys(value).sort();
    const sortedExpected = [...expected].sort();
    if (
        actual.length !== sortedExpected.length
        || actual.some((key, index) => key !== sortedExpected[index])
    ) {
        throw new Error(code);
    }
}
