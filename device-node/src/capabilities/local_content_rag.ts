/**
 * Local Content RAG - Device Node Capability
 *
 * Watches local files, generates embeddings, and provides semantic search.
 */

import * as path from "path";
import { watch, type FSWatcher } from "chokidar";

import { ContentChunker } from "./local_content_rag_chunker.js";
import { EmbeddingProvider } from "./local_content_rag_embeddings.js";
import { LocalVectorStore } from "./local_content_rag_store.js";
import type { LocalContentConfig, SearchResult } from "./local_content_rag_types.js";

export type { ContentChunk, LocalContentConfig, SearchResult } from "./local_content_rag_types.js";
export { ContentChunker } from "./local_content_rag_chunker.js";
export { EmbeddingProvider } from "./local_content_rag_embeddings.js";
export { LocalVectorStore } from "./local_content_rag_store.js";

export class LocalContentIndexService {
    private config: LocalContentConfig;
    private chunker: ContentChunker;
    private embedder: EmbeddingProvider;
    private store: LocalVectorStore;
    private watcher?: FSWatcher;
    private fileExtensions: Set<string>;

    constructor(config: LocalContentConfig) {
        this.config = config;
        this.chunker = new ContentChunker(config.chunkSize, config.chunkOverlap);
        this.embedder = new EmbeddingProvider(config);
        this.store = new LocalVectorStore(config.dbPath);
        this.fileExtensions = new Set(config.fileExtensions || [".md", ".txt", ".json"]);
    }

    /**
     * Start watching directories for file changes.
     */
    startWatching(): void {
        if (this.watcher) {
            this.watcher.close();
        }

        const patterns = this.config.watchDirs.map(dir =>
            `${dir}/**/*{${Array.from(this.fileExtensions).join(",")}}`
        );

        this.watcher = watch(patterns, {
            ignored: /(^|[\/\\])\../,
            persistent: true,
            ignoreInitial: false,
        });

        this.watcher
            .on("add", (filePath) => this.indexFile(filePath))
            .on("change", (filePath) => this.indexFile(filePath))
            .on("unlink", (filePath) => this.store.deleteByFilePath(filePath));

        console.log(`[LocalContentRAG] Watching: ${this.config.watchDirs.join(", ")}`);
    }

    /**
     * Stop watching directories.
     */
    stopWatching(): void {
        if (this.watcher) {
            this.watcher.close();
            this.watcher = undefined;
        }
    }

    /**
     * Index a single file.
     */
    async indexFile(filePath: string): Promise<number> {
        try {
            const chunks = await this.chunker.chunkFile(filePath);
            let indexed = 0;

            for (const chunk of chunks) {
                try {
                    chunk.embedding = await this.embedder.generateEmbedding(chunk.content);
                    await this.store.upsertChunk(chunk);
                    indexed++;
                } catch (error) {
                    console.error(`[LocalContentRAG] Failed to embed chunk from ${filePath}:`, error);
                }
            }

            console.log(`[LocalContentRAG] Indexed ${indexed} chunks from ${path.basename(filePath)}`);
            return indexed;
        } catch (error) {
            console.error(`[LocalContentRAG] Failed to index ${filePath}:`, error);
            return 0;
        }
    }

    /**
     * Search for relevant content.
     */
    async search(query: string, topK: number = 5): Promise<SearchResult[]> {
        const queryEmbedding = await this.embedder.generateEmbedding(query);
        return this.store.search(queryEmbedding, topK);
    }

    /**
     * Get index statistics.
     */
    getStats(): { totalChunks: number; totalFiles: number; watchDirs: string[] } {
        const dbStats = this.store.getStats();
        return {
            ...dbStats,
            watchDirs: this.config.watchDirs,
        };
    }

    /**
     * Close resources.
     */
    close(): void {
        this.stopWatching();
        this.store.close();
    }
}

let indexService: LocalContentIndexService | null = null;

export function initLocalContentRAG(config: LocalContentConfig): void {
    if (indexService) {
        indexService.close();
    }
    indexService = new LocalContentIndexService(config);
    indexService.startWatching();
}

export async function localSearch(args: { query: string; topK?: number }): Promise<{
    results: Array<{
        filePath: string;
        content: string;
        score: number;
        startLine: number;
        endLine: number;
        metadata: Record<string, unknown>;
    }>;
    stats: { totalChunks: number; totalFiles: number };
}> {
    if (!indexService) {
        throw new Error("LocalContentRAG not initialized");
    }

    const results = await indexService.search(args.query, args.topK || 5);

    return {
        results: results.map(r => ({
            filePath: r.chunk.filePath,
            content: r.chunk.content,
            score: r.score,
            startLine: r.chunk.startLine,
            endLine: r.chunk.endLine,
            metadata: r.chunk.metadata,
        })),
        stats: indexService.getStats(),
    };
}

export function getLocalContentStats(): {
    totalChunks: number;
    totalFiles: number;
    watchDirs: string[];
} {
    if (!indexService) {
        return { totalChunks: 0, totalFiles: 0, watchDirs: [] };
    }
    return indexService.getStats();
}
