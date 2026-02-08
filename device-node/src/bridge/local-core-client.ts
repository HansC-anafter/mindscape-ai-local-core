/**
 * Local-Core Bridge
 *
 * WebSocket client for connecting to Mindscape Local-Core.
 * Handles user confirmation requests with nonce binding and audit event reporting.
 */

import WebSocket from "ws";
import * as crypto from "crypto";
import { TrustLevel } from "../governance/permission-map.js";

export interface ConfirmationRequest {
    nonce: string;
    tool_call_id: string;
    tool: string;
    arguments: Record<string, unknown>;
    arguments_hash: string;
    trustLevel: TrustLevel;
    preview?: string;
    expires_at: number;
}

export interface ConfirmationResponse {
    nonce: string;
    tool_call_id: string;
    arguments_hash: string;
    approved: boolean;
}

export interface AuditEvent {
    tool: string;
    arguments: Record<string, unknown>;
    result: "success" | "error";
    error?: string;
    trustLevel: TrustLevel;
}

export class LocalCoreBridge {
    private url: string;
    private ws: WebSocket | null = null;
    private pendingConfirmations: Map<string, {
        request: ConfirmationRequest;
        resolve: (value: boolean) => void;
        reject: (reason: Error) => void;
    }> = new Map();
    private messageId = 0;

    constructor(url: string) {
        this.url = url;
    }

    async connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.url);

                this.ws.on("open", () => {
                    console.log("🔗 Connected to Local-Core");
                    resolve();
                });

                this.ws.on("message", (data) => {
                    this.handleMessage(data.toString());
                });

                this.ws.on("error", (error) => {
                    console.error("WebSocket error:", error);
                    reject(error);
                });

                this.ws.on("close", () => {
                    console.log("🔌 Disconnected from Local-Core");
                    this.ws = null;
                });
            } catch (error) {
                reject(error);
            }
        });
    }

    async disconnect(): Promise<void> {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Generate cryptographic hash of arguments for binding
     */
    private hashArguments(args: Record<string, unknown>): string {
        const json = JSON.stringify(args, Object.keys(args).sort());
        return crypto.createHash("sha256").update(json).digest("hex");
    }

    /**
     * Request user confirmation with nonce binding
     */
    async requestConfirmation(params: {
        tool: string;
        arguments: Record<string, unknown>;
        trustLevel: TrustLevel;
        preview?: string;
    }): Promise<boolean> {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn("Local-Core not connected, auto-denying confirmation");
            return false;
        }

        const nonce = crypto.randomUUID();
        const tool_call_id = `tc_${crypto.randomUUID()}`;
        const arguments_hash = this.hashArguments(params.arguments);
        const expires_at = Date.now() + 60000;

        const request: ConfirmationRequest = {
            nonce,
            tool_call_id,
            tool: params.tool,
            arguments: params.arguments,
            arguments_hash,
            trustLevel: params.trustLevel,
            preview: params.preview,
            expires_at,
        };

        return new Promise((resolve, reject) => {
            this.pendingConfirmations.set(nonce, { request, resolve, reject });

            const message = {
                type: "confirmation_request",
                payload: {
                    nonce: request.nonce,
                    tool_call_id: request.tool_call_id,
                    tool: request.tool,
                    arguments: request.arguments,
                    arguments_hash: request.arguments_hash,
                    trustLevel: TrustLevel[request.trustLevel],
                    preview: request.preview,
                    expires_at: request.expires_at,
                },
            };

            this.ws!.send(JSON.stringify(message));

            setTimeout(() => {
                if (this.pendingConfirmations.has(nonce)) {
                    this.pendingConfirmations.delete(nonce);
                    console.warn(`Confirmation timed out for ${params.tool}`);
                    resolve(false);
                }
            }, 60000);
        });
    }

    /**
     * Validate confirmation response matches original request
     */
    private validateConfirmationResponse(
        request: ConfirmationRequest,
        response: ConfirmationResponse
    ): boolean {
        if (request.nonce !== response.nonce) {
            console.error("Nonce mismatch");
            return false;
        }
        if (request.tool_call_id !== response.tool_call_id) {
            console.error("Tool call ID mismatch");
            return false;
        }
        if (request.arguments_hash !== response.arguments_hash) {
            console.error("Arguments hash mismatch - potential tampering");
            return false;
        }
        if (Date.now() > request.expires_at) {
            console.error("Confirmation expired");
            return false;
        }
        return true;
    }

    async reportAuditEvent(event: AuditEvent): Promise<void> {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log("Audit event (offline):", event);
            return;
        }

        const message = {
            type: "audit_event",
            payload: {
                tool: event.tool,
                arguments_hash: this.hashArguments(event.arguments),
                result: event.result,
                error: event.error,
                trustLevel: TrustLevel[event.trustLevel],
                timestamp: new Date().toISOString(),
            },
        };

        this.ws.send(JSON.stringify(message));
    }

    private handleMessage(data: string): void {
        try {
            const message = JSON.parse(data);

            if (message.type === "confirmation_response") {
                const response: ConfirmationResponse = message.payload;
                const pending = this.pendingConfirmations.get(response.nonce);

                if (pending) {
                    this.pendingConfirmations.delete(response.nonce);

                    if (this.validateConfirmationResponse(pending.request, response)) {
                        pending.resolve(response.approved === true);
                    } else {
                        pending.resolve(false);
                    }
                }
            }
        } catch (error) {
            console.error("Failed to parse message from Local-Core:", error);
        }
    }
}
