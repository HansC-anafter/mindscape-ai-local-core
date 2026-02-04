/**
 * ConfirmGuard - Confirmation Token Service
 *
 * Manages confirm_token generation and validation for governed tool operations.
 * Tokens are short-lived and tied to specific workspace + tool combinations.
 */
import { MindscapeClient } from "./mindscape/client.js";
import { config } from "./config.js";

export interface ConfirmRequest {
    workspace_id: string;
    tool_name: string;
    action_preview?: string;
    inputs?: Record<string, any>;
    expires_in_seconds?: number;
}

export interface ConfirmToken {
    token: string;
    workspace_id: string;
    tool_name: string;
    action_preview?: string;
    expires_at: string;
    created_at: string;
}

export interface ConfirmValidation {
    valid: boolean;
    reason?: string;
    token_info?: ConfirmToken;
}

// In-memory token store (for MVP; production should use Redis/DB)
const tokenStore = new Map<string, ConfirmToken>();

export class ConfirmGuard {
    private defaultExpirySeconds = 300; // 5 minutes

    constructor(private client: MindscapeClient) { }

    /**
     * Generate a confirmation token for a governed operation.
     */
    generateToken(request: ConfirmRequest): ConfirmToken {
        const tokenId = this.generateTokenId();
        const expiresInSeconds = request.expires_in_seconds || this.defaultExpirySeconds;
        const now = new Date();
        const expiresAt = new Date(now.getTime() + expiresInSeconds * 1000);

        const token: ConfirmToken = {
            token: tokenId,
            workspace_id: request.workspace_id,
            tool_name: request.tool_name,
            action_preview: request.action_preview,
            expires_at: expiresAt.toISOString(),
            created_at: now.toISOString()
        };

        tokenStore.set(tokenId, token);

        // Clean up expired tokens periodically
        this.cleanupExpiredTokens();

        return token;
    }

    /**
     * Validate a confirmation token.
     */
    validateToken(
        tokenId: string,
        workspace_id: string,
        tool_name: string
    ): ConfirmValidation {
        const token = tokenStore.get(tokenId);

        if (!token) {
            return {
                valid: false,
                reason: "Token not found or expired"
            };
        }

        // Check expiry
        const now = new Date();
        const expiresAt = new Date(token.expires_at);
        if (now > expiresAt) {
            tokenStore.delete(tokenId);
            return {
                valid: false,
                reason: "Token has expired"
            };
        }

        // Check workspace match
        if (token.workspace_id !== workspace_id) {
            return {
                valid: false,
                reason: "Token workspace mismatch"
            };
        }

        // Check tool match
        if (token.tool_name !== tool_name) {
            return {
                valid: false,
                reason: `Token was issued for tool '${token.tool_name}', not '${tool_name}'`
            };
        }

        // Valid - consume the token (one-time use)
        tokenStore.delete(tokenId);

        return {
            valid: true,
            token_info: token
        };
    }

    /**
     * Build action preview message for confirmation request.
     */
    buildActionPreview(toolName: string, inputs: Record<string, any>): string {
        const inputsSummary = Object.entries(inputs)
            .map(([key, value]) => {
                const displayValue = typeof value === "object"
                    ? JSON.stringify(value).substring(0, 50) + "..."
                    : String(value).substring(0, 50);
                return `  - ${key}: ${displayValue}`;
            })
            .join("\n");

        return `Tool: ${toolName}\nInputs:\n${inputsSummary}`;
    }

    /**
     * Generate unique token ID.
     */
    private generateTokenId(): string {
        const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        let result = "cfm_";
        for (let i = 0; i < 32; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    }

    /**
     * Clean up expired tokens.
     */
    private cleanupExpiredTokens(): void {
        const now = new Date();
        for (const [tokenId, token] of tokenStore.entries()) {
            const expiresAt = new Date(token.expires_at);
            if (now > expiresAt) {
                tokenStore.delete(tokenId);
            }
        }
    }

    /**
     * Get token count (for monitoring).
     */
    getActiveTokenCount(): number {
        this.cleanupExpiredTokens();
        return tokenStore.size;
    }
}
