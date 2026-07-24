import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import test from "node:test";

import {
    ensureReceiverRuntime,
    type ReceiverRuntime,
} from "./receiver-runtime.js";

function createRuntime(root: string, preflightSource: string): ReceiverRuntime {
    const scripts = path.join(root, "scripts");
    mkdirSync(scripts, { recursive: true });
    const runtime: ReceiverRuntime = {
        root,
        python: process.execPath,
        script: path.join(scripts, "live_motion_receiver.py"),
        preflightScript: path.join(scripts, "verify_live_motion_receiver_runtime.py"),
    };
    writeFileSync(runtime.script, "# receiver fixture\n");
    writeFileSync(runtime.preflightScript, preflightSource);
    return runtime;
}

test("caches a successful preflight for an unchanged receiver runtime", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "receiver-runtime-"));
    const counterPath = path.join(root, "preflight-count.txt");
    const runtime = createRuntime(
        root,
        [
            "const fs = require('node:fs');",
            `const file = ${JSON.stringify(counterPath)};`,
            "const count = Number(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : 0);",
            "fs.writeFileSync(file, String(count + 1));",
        ].join("\n"),
    );

    try {
        await ensureReceiverRuntime(runtime, 1000);
        await ensureReceiverRuntime(runtime, 2000);
        assert.equal(readFileSync(counterPath, "utf8"), "1");
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

test("shares one in-flight preflight for concurrent receiver starts", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "receiver-runtime-"));
    const counterPath = path.join(root, "preflight-count.txt");
    const runtime = createRuntime(
        root,
        [
            "const fs = require('node:fs');",
            `const file = ${JSON.stringify(counterPath)};`,
            "const count = Number(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : 0);",
            "fs.writeFileSync(file, String(count + 1));",
            "setTimeout(() => process.exit(0), 75);",
        ].join("\n"),
    );

    try {
        await Promise.all([
            ensureReceiverRuntime(runtime, 3000),
            ensureReceiverRuntime(runtime, 3000),
        ]);
        assert.equal(readFileSync(counterPath, "utf8"), "1");
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});

test("fails closed with a stable reason when runtime preflight times out", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "receiver-runtime-"));
    const runtime = createRuntime(root, "setInterval(() => {}, 1000);\n");

    try {
        await assert.rejects(
            ensureReceiverRuntime(runtime, 4000, 25),
            /live_media_receiver_runtime_preflight_timeout/,
        );
    } finally {
        rmSync(root, { recursive: true, force: true });
    }
});
