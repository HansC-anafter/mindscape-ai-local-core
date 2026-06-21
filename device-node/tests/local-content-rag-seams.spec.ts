import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";

import {
    ContentChunker,
    EmbeddingProvider,
    LocalVectorStore,
    localSearch,
    type ContentChunk,
} from "../src/capabilities/local_content_rag.js";

async function withTempDir<T>(callback: (dir: string) => Promise<T>): Promise<T> {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "local-content-rag-"));
    try {
        return await callback(dir);
    } finally {
        await fs.rm(dir, { recursive: true, force: true });
    }
}

test("ContentChunker keeps markdown sections and deterministic chunk metadata", async () => {
    await withTempDir(async (dir) => {
        const filePath = path.join(dir, "notes.md");
        await fs.writeFile(filePath, "# Intro\nalpha\n# Next\nbeta\n", "utf-8");

        const chunks = await new ContentChunker(200, 0).chunkFile(filePath);

        assert.equal(chunks.length, 2);
        assert.equal(chunks[0].filePath, filePath);
        assert.equal(chunks[0].content, "# Intro\nalpha");
        assert.equal(chunks[0].startLine, 1);
        assert.equal(chunks[0].endLine, 2);
        assert.equal(chunks[0].metadata.title, "notes.md");
        assert.equal(chunks[0].metadata.section, "Intro");
        assert.equal(chunks[0].metadata.fileType, "markdown");
        assert.match(chunks[0].id, /^[a-f0-9]{16}$/);
        assert.equal(chunks[1].metadata.section, "Next");
    });
});

test("EmbeddingProvider can generate Ollama embeddings through mocked fetch", async () => {
    const calls: Array<{ input: Parameters<typeof fetch>[0]; init?: Parameters<typeof fetch>[1] }> = [];
    const fetchImpl: typeof fetch = async (input, init) => {
        calls.push({ input, init });
        return new Response(JSON.stringify({ embedding: [0.25, 0.5] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
        });
    };

    const provider = new EmbeddingProvider(
        {
            embeddingProvider: "ollama",
            ollamaUrl: "http://ollama.local",
            ollamaModel: "test-model",
        },
        fetchImpl
    );

    const embedding = await provider.generateEmbedding("x".repeat(8100));

    assert.deepEqual(embedding, [0.25, 0.5]);
    assert.equal(calls.length, 1);
    assert.equal(String(calls[0].input), "http://ollama.local/api/embeddings");
    const body = JSON.parse(String(calls[0].init?.body));
    assert.equal(body.model, "test-model");
    assert.equal(body.prompt.length, 8000);
});

test("LocalVectorStore upserts searchable chunks and reports stats from a temp database", async () => {
    await withTempDir(async (dir) => {
        const dbPath = path.join(dir, "rag.sqlite");
        let store: LocalVectorStore | undefined;

        const first: ContentChunk = {
            id: "first",
            filePath: "/tmp/first.txt",
            content: "alpha",
            startLine: 1,
            endLine: 1,
            embedding: [1, 0],
            metadata: {
                fileType: "text",
                modifiedAt: "2026-06-22T00:00:00.000Z",
            },
        };
        const second: ContentChunk = {
            id: "second",
            filePath: "/tmp/second.txt",
            content: "beta",
            startLine: 1,
            endLine: 1,
            embedding: [0, 1],
            metadata: {
                fileType: "text",
                modifiedAt: "2026-06-22T00:00:00.000Z",
            },
        };

        try {
            store = new LocalVectorStore(dbPath);
            await store.upsertChunk(first);
            await store.upsertChunk(second);

            assert.deepEqual(store.getStats(), { totalChunks: 2, totalFiles: 2 });

            const results = await store.search([1, 0], 1);
            assert.equal(results.length, 1);
            assert.equal(results[0].chunk.id, "first");
        } finally {
            store?.close();
        }
    });
});

test("localSearch keeps the uninitialized public API error", async () => {
    await assert.rejects(
        () => localSearch({ query: "alpha" }),
        /LocalContentRAG not initialized/
    );
});
