import type { IncomingMessage, Server, ServerResponse } from "http";
import type { Duplex } from "stream";

const DEFAULT_MAX_BODY_BYTES = 5_000_000;

export class RequestAbortedError extends Error {
    code = "REQUEST_ABORTED";

    constructor(message = "Request aborted by client") {
        super(message);
        this.name = "RequestAbortedError";
    }
}

export class RequestBodyTooLargeError extends Error {
    code = "REQUEST_BODY_TOO_LARGE";

    constructor(maxBytes: number) {
        super(`Request body exceeds ${maxBytes} bytes`);
        this.name = "RequestBodyTooLargeError";
    }
}

function errorCode(error: unknown): string | null {
    if (typeof error !== "object" || error === null || !("code" in error)) {
        return null;
    }
    const code = (error as { code?: unknown }).code;
    return typeof code === "string" ? code : null;
}

export function normalizeRequestError(error: unknown): Error {
    if (error instanceof RequestAbortedError) {
        return error;
    }
    if (errorCode(error) === "ECONNRESET") {
        return new RequestAbortedError();
    }
    if (error instanceof Error) {
        return error;
    }
    return new Error(String(error));
}

export function isRequestAbortedError(error: unknown): boolean {
    return error instanceof RequestAbortedError || errorCode(error) === "ECONNRESET";
}

export function readRequestBody(
    req: IncomingMessage,
    maxBytes = DEFAULT_MAX_BODY_BYTES,
): Promise<string> {
    return new Promise((resolve, reject) => {
        let body = "";
        let bytes = 0;
        let settled = false;

        const cleanup = (): void => {
            req.off("data", onData);
            req.off("end", onEnd);
            req.off("aborted", onAborted);
            req.off("error", onError);
        };

        const settle = (callback: () => void): void => {
            if (settled) {
                return;
            }
            settled = true;
            cleanup();
            callback();
        };

        const onData = (chunk: string | Buffer): void => {
            const text = typeof chunk === "string" ? chunk : chunk.toString("utf-8");
            bytes += Buffer.byteLength(text);
            if (bytes > maxBytes) {
                settle(() => reject(new RequestBodyTooLargeError(maxBytes)));
                return;
            }
            body += text;
        };

        const onEnd = (): void => {
            settle(() => resolve(body));
        };

        const onAborted = (): void => {
            settle(() => reject(new RequestAbortedError()));
        };

        const onError = (error: Error): void => {
            settle(() => reject(normalizeRequestError(error)));
        };

        if (req.aborted) {
            reject(new RequestAbortedError());
            return;
        }

        req.setEncoding("utf8");
        req.on("data", onData);
        req.on("end", onEnd);
        req.on("aborted", onAborted);
        req.on("error", onError);
    });
}

export function writeJsonResponse(
    res: ServerResponse,
    statusCode: number,
    payload: unknown,
): boolean {
    if (res.destroyed || res.writableEnded) {
        return false;
    }
    res.writeHead(statusCode, { "Content-Type": "application/json" });
    res.end(JSON.stringify(payload));
    return true;
}

export function writeJsonRpcError(
    res: ServerResponse,
    message: string,
    id: string | number | null = null,
): boolean {
    return writeJsonResponse(res, 200, {
        jsonrpc: "2.0",
        id,
        error: {
            code: -32000,
            message,
        },
    });
}

function closeClientErrorSocket(socket: Duplex): void {
    try {
        if (!socket.destroyed && socket.writable) {
            socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
            return;
        }
    } catch {
        // Socket cleanup must not escape the HTTP server boundary.
    }
    socket.destroy();
}

export function attachHttpServerErrorHandlers(server: Server): void {
    server.on("clientError", (_error, socket) => {
        closeClientErrorSocket(socket);
    });
}
