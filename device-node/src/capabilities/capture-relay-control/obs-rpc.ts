import { createHash } from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import WebSocket from "ws";

import type { ObsRpcClient, ObsWebSocketMessage } from "./types.js";

function obsWebsocketConfigPath(): string {
    return path.join(
        os.homedir(),
        "Library",
        "Application Support",
        "obs-studio",
        "plugin_config",
        "obs-websocket",
        "config.json",
    );
}

function readObsWebsocketPassword(): string | null {
    const configuredPassword = String(process.env.CAPTURE_RELAY_OBS_WEBSOCKET_PASSWORD || "").trim();
    if (configuredPassword) {
        return configuredPassword;
    }
    try {
        const config = JSON.parse(fs.readFileSync(obsWebsocketConfigPath(), "utf-8")) as Record<string, unknown>;
        const password = String(config.server_password || "").trim();
        return password || null;
    } catch {
        return null;
    }
}

function obsAuthResponse(password: string, salt: string, challenge: string): string {
    const secret = createHash("sha256")
        .update(password + salt)
        .digest("base64");
    return createHash("sha256")
        .update(secret + challenge)
        .digest("base64");
}

function parseObsMessage(data: WebSocket.RawData): ObsWebSocketMessage {
    return JSON.parse(data.toString("utf-8")) as ObsWebSocketMessage;
}

function waitForSocketOpen(socket: WebSocket, timeoutMs: number): Promise<void> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("obs_websocket_open_timeout")), timeoutMs);
        socket.once("open", () => {
            clearTimeout(timer);
            resolve();
        });
        socket.once("error", (error) => {
            clearTimeout(timer);
            reject(error);
        });
    });
}

export async function createObsRpcClient(host: string, port: number, timeoutMs: number): Promise<ObsRpcClient> {
    const socket = new WebSocket(`ws://${host}:${port}`);
    const queuedMessages: ObsWebSocketMessage[] = [];
    const queuedWaiters: Array<{
        resolve: (message: ObsWebSocketMessage) => void;
        reject: (error: Error) => void;
        timer: NodeJS.Timeout;
    }> = [];
    const queueMessage = (data: WebSocket.RawData) => {
        let message: ObsWebSocketMessage;
        try {
            message = parseObsMessage(data);
        } catch (error) {
            const waiter = queuedWaiters.shift();
            if (waiter) {
                clearTimeout(waiter.timer);
                waiter.reject(error instanceof Error ? error : new Error(String(error)));
            }
            return;
        }
        const waiter = queuedWaiters.shift();
        if (waiter) {
            clearTimeout(waiter.timer);
            waiter.resolve(message);
            return;
        }
        queuedMessages.push(message);
    };
    const nextQueuedMessage = () => new Promise<ObsWebSocketMessage>((resolve, reject) => {
        const message = queuedMessages.shift();
        if (message) {
            resolve(message);
            return;
        }
        const timer = setTimeout(() => {
            const index = queuedWaiters.findIndex((waiter) => waiter.timer === timer);
            if (index >= 0) {
                queuedWaiters.splice(index, 1);
            }
            reject(new Error("obs_websocket_message_timeout"));
        }, timeoutMs);
        queuedWaiters.push({ resolve, reject, timer });
    });
    socket.on("message", queueMessage);
    await waitForSocketOpen(socket, timeoutMs);
    const hello = await nextQueuedMessage();
    if (hello.op !== 0) {
        socket.close();
        throw new Error("obs_websocket_unexpected_hello");
    }

    const helloData = hello.d || {};
    const authentication = helloData.authentication as Record<string, unknown> | undefined;
    const identify: Record<string, unknown> = {
        rpcVersion: 1,
        eventSubscriptions: 0,
    };
    if (authentication) {
        const password = readObsWebsocketPassword();
        const salt = String(authentication.salt || "");
        const challenge = String(authentication.challenge || "");
        if (!password || !salt || !challenge) {
            socket.close();
            throw new Error("obs_websocket_auth_missing");
        }
        identify.authentication = obsAuthResponse(password, salt, challenge);
    }

    socket.send(JSON.stringify({ op: 1, d: identify }));
    const identified = await nextQueuedMessage();
    if (identified.op !== 2) {
        socket.close();
        throw new Error("obs_websocket_identify_failed");
    }
    socket.off("message", queueMessage);

    let requestSeq = 0;
    const pending = new Map<string, {
        resolve: (value: Record<string, unknown>) => void;
        reject: (error: Error) => void;
        timer: NodeJS.Timeout;
    }>();

    socket.on("message", (data) => {
        let message: ObsWebSocketMessage;
        try {
            message = parseObsMessage(data);
        } catch {
            return;
        }
        if (message.op !== 7) {
            return;
        }
        const payload = message.d || {};
        const requestId = String(payload.requestId || "");
        const request = pending.get(requestId);
        if (!request) {
            return;
        }
        clearTimeout(request.timer);
        pending.delete(requestId);
        const status = payload.requestStatus as Record<string, unknown> | undefined;
        if (status?.result === true) {
            request.resolve((payload.responseData as Record<string, unknown> | undefined) || {});
            return;
        }
        request.reject(new Error(String(status?.comment || status?.code || "obs_request_failed")));
    });

    return {
        request(requestType: string, requestData: Record<string, unknown> = {}) {
            const requestId = `capture-relay-${Date.now()}-${++requestSeq}`;
            const timer = setTimeout(() => {
                const request = pending.get(requestId);
                if (!request) {
                    return;
                }
                pending.delete(requestId);
                request.reject(new Error(`obs_request_timeout:${requestType}`));
            }, timeoutMs);
            const promise = new Promise<Record<string, unknown>>((resolve, reject) => {
                pending.set(requestId, { resolve, reject, timer });
            });
            socket.send(JSON.stringify({
                op: 6,
                d: {
                    requestType,
                    requestId,
                    requestData,
                },
            }));
            return promise;
        },
        close() {
            for (const request of pending.values()) {
                clearTimeout(request.timer);
                request.reject(new Error("obs_websocket_closed"));
            }
            pending.clear();
            socket.close();
        },
    };
}
