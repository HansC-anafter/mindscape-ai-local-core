/**
 * Local Content RAG - Device Node Capability
 *
 * Watches local files, generates embeddings, and provides semantic search.
 *
 * Features:
 * - FileWatcher: Monitor directories for changes
 * - ContentChunker: Split documents into searchable chunks
 * - EmbeddingProvider: Ollama (local) or OpenAI (BYOK)
 * - LocalVectorStore: SQLite-based vector storage
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import * as crypto from 'crypto';
import Database from 'better-sqlite3';
import { watch, FSWatcher } from 'chokidar';

// ============================================================================
// Types
// ============================================================================

export interface ContentChunk {
    id: string;
    filePath: string;
    content: string;
    startLine: number;
    endLine: number;
    embedding?: number[];
    metadata: {
        title?: string;
        section?: string;
        fileType: string;
        modifiedAt: string;
    };
}

export interface SearchResult {
    chunk: ContentChunk;
    score: number;
}

export interface LocalContentConfig {
    watchDirs: string[];
    embeddingProvider: 'ollama' | 'openai';
    ollamaUrl?: string;
    ollamaModel?: string;
    openaiApiKey?: string;
    dbPath: string;
    chunkSize?: number;
    chunkOverlap?: number;
    fileExtensions?: string[];
}

// ============================================================================
// Content Chunker
// ============================================================================

export class ContentChunker {
    private chunkSize: number;
    private chunkOverlap: number;

    constructor(chunkSize = 500, chunkOverlap = 100) {
        this.chunkSize = chunkSize;
        this.chunkOverlap = chunkOverlap;
    }

    /**
     * Split content into chunks based on file type
     */
    async chunkFile(filePath: string): Promise<ContentChunk[]> {
        const ext = path.extname(filePath).toLowerCase();
        const content = await fs.readFile(filePath, 'utf-8');
        const stat = await fs.stat(filePath);

        switch (ext) {
            case '.md':
                return this.chunkMarkdown(filePath, content, stat.mtime.toISOString());
            case '.txt':
                return this.chunkPlainText(filePath, content, stat.mtime.toISOString());
            case '.json':
                return this.chunkJson(filePath, content, stat.mtime.toISOString());
            default:
                return this.chunkPlainText(filePath, content, stat.mtime.toISOString());
        }
    }

    private chunkMarkdown(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        const chunks: ContentChunk[] = [];
        const lines = content.split('\n');

        let currentSection = '';
        let currentChunk = '';
        let startLine = 1;
        let lineNum = 1;

        for (const line of lines) {
            // Detect markdown headers
            if (line.startsWith('#')) {
                // Save previous chunk if exists
                if (currentChunk.trim()) {
                    chunks.push(this.createChunk(
                        filePath, currentChunk, startLine, lineNum - 1,
                        'markdown', modifiedAt, currentSection
                    ));
                }
                currentSection = line.replace(/^#+\s*/, '');
                currentChunk = line + '\n';
                startLine = lineNum;
            } else {
                currentChunk += line + '\n';

                // Check if chunk is too large
                if (currentChunk.length > this.chunkSize) {
                    chunks.push(this.createChunk(
                        filePath, currentChunk, startLine, lineNum,
                        'markdown', modifiedAt, currentSection
                    ));
                    currentChunk = '';
                    startLine = lineNum + 1;
                }
            }
            lineNum++;
        }

        // Add remaining content
        if (currentChunk.trim()) {
            chunks.push(this.createChunk(
                filePath, currentChunk, startLine, lineNum - 1,
                'markdown', modifiedAt, currentSection
            ));
        }

        return chunks;
    }

    private chunkPlainText(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        const chunks: ContentChunk[] = [];
        const lines = content.split('\n');

        let currentChunk = '';
        let startLine = 1;

        for (let i = 0; i < lines.length; i++) {
            currentChunk += lines[i] + '\n';

            if (currentChunk.length >= this.chunkSize) {
                chunks.push(this.createChunk(
                    filePath, currentChunk, startLine, i + 1,
                    'text', modifiedAt
                ));

                // Handle overlap
                const overlapLines = Math.ceil(this.chunkOverlap / 50);
                startLine = Math.max(1, i + 1 - overlapLines);
                currentChunk = lines.slice(startLine - 1, i + 1).join('\n') + '\n';
            }
        }

        if (currentChunk.trim()) {
            chunks.push(this.createChunk(
                filePath, currentChunk, startLine, lines.length,
                'text', modifiedAt
            ));
        }

        return chunks;
    }

    private chunkJson(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        // For JSON, treat as single chunk with stringified content
        try {
            const parsed = JSON.parse(content);
            const readable = JSON.stringify(parsed, null, 2);
            return [this.createChunk(filePath, readable, 1, 1, 'json', modifiedAt)];
        } catch {
            return this.chunkPlainText(filePath, content, modifiedAt);
        }
    }

    private createChunk(
        filePath: string,
        content: string,
        startLine: number,
        endLine: number,
        fileType: string,
        modifiedAt: string,
        section?: string
    ): ContentChunk {
        const id = crypto.createHash('sha256')
            .update(`${filePath}:${startLine}:${endLine}`)
            .digest('hex')
            .substring(0, 16);

        return {
            id,
            filePath,
            content: content.trim(),
            startLine,
            endLine,
            metadata: {
                title: path.basename(filePath),
                section,
                fileType,
                modifiedAt,
            },
        };
    }
}

// ============================================================================
// Embedding Provider
// ============================================================================

export class EmbeddingProvider {
    private provider: 'ollama' | 'openai';
    private ollamaUrl: string;
    private ollamaModel: string;
    private openaiApiKey?: string;

    constructor(config: Partial<LocalContentConfig>) {
        this.provider = config.embeddingProvider || 'ollama';
        this.ollamaUrl = config.ollamaUrl || 'http://localhost:11434';
        this.ollamaModel = config.ollamaModel || 'nomic-embed-text';
        this.openaiApiKey = config.openaiApiKey;
    }

    async generateEmbedding(text: string): Promise<number[]> {
        if (this.provider === 'openai') {
            return this.embedOpenAI(text);
        }
        return this.embedOllama(text);
    }

    private async embedOllama(text: string): Promise<number[]> {
        const response = await fetch(`${this.ollamaUrl}/api/embeddings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: this.ollamaModel,
                prompt: text.substring(0, 8000), // Limit input size
            }),
        });

        if (!response.ok) {
            throw new Error(`Ollama embedding failed: ${response.statusText}`);
        }

        const data = await response.json() as { embedding: number[] };
        return data.embedding;
    }

    private async embedOpenAI(text: string): Promise<number[]> {
        if (!this.openaiApiKey) {
            throw new Error('OpenAI API key not configured');
        }

        const response = await fetch('https://api.openai.com/v1/embeddings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.openaiApiKey}`,
            },
            body: JSON.stringify({
                model: 'text-embedding-3-small',
                input: text.substring(0, 8000),
            }),
        });

        if (!response.ok) {
            throw new Error(`OpenAI embedding failed: ${response.statusText}`);
        }

        const data = await response.json() as { data: Array<{ embedding: number[] }> };
        return data.data[0].embedding;
    }
}

// ============================================================================
// Local Vector Store (SQLite)
// ============================================================================

export class LocalVectorStore {
    private db: Database.Database;

    constructor(dbPath: string) {
        this.db = new Database(dbPath);
        this.initSchema();
    }

    private initSchema(): void {
        this.db.exec(`
      CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        content TEXT NOT NULL,
        start_line INTEGER,
        end_line INTEGER,
        embedding BLOB,
        metadata TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path);
      CREATE INDEX IF NOT EXISTS idx_chunks_updated_at ON chunks(updated_at);
    `);
    }

    async upsertChunk(chunk: ContentChunk): Promise<void> {
        const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO chunks (id, file_path, content, start_line, end_line, embedding, metadata, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

        stmt.run(
            chunk.id,
            chunk.filePath,
            chunk.content,
            chunk.startLine,
            chunk.endLine,
            chunk.embedding ? Buffer.from(new Float32Array(chunk.embedding).buffer) : null,
            JSON.stringify(chunk.metadata),
            new Date().toISOString()
        );
    }

    async deleteByFilePath(filePath: string): Promise<void> {
        this.db.prepare('DELETE FROM chunks WHERE file_path = ?').run(filePath);
    }

    async search(queryEmbedding: number[], topK: number = 5): Promise<SearchResult[]> {
        // Get all chunks with embeddings
        const rows = this.db.prepare(`
      SELECT id, file_path, content, start_line, end_line, embedding, metadata
      FROM chunks
      WHERE embedding IS NOT NULL
    `).all() as Array<{
            id: string;
            file_path: string;
            content: string;
            start_line: number;
            end_line: number;
            embedding: Buffer;
            metadata: string;
        }>;

        // Compute similarities
        const results: SearchResult[] = [];

        for (const row of rows) {
            const embedding = Array.from(new Float32Array(row.embedding.buffer));
            const score = this.cosineSimilarity(queryEmbedding, embedding);

            results.push({
                chunk: {
                    id: row.id,
                    filePath: row.file_path,
                    content: row.content,
                    startLine: row.start_line,
                    endLine: row.end_line,
                    embedding,
                    metadata: JSON.parse(row.metadata),
                },
                score,
            });
        }

        // Sort and return top K
        return results
            .sort((a, b) => b.score - a.score)
            .slice(0, topK);
    }

    private cosineSimilarity(a: number[], b: number[]): number {
        if (a.length !== b.length) return 0;

        let dot = 0, normA = 0, normB = 0;
        for (let i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }

        if (normA === 0 || normB === 0) return 0;
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    getStats(): { totalChunks: number; totalFiles: number } {
        const stats = this.db.prepare(`
      SELECT COUNT(*) as total_chunks, COUNT(DISTINCT file_path) as total_files
      FROM chunks
    `).get() as { total_chunks: number; total_files: number };

        return {
            totalChunks: stats.total_chunks,
            totalFiles: stats.total_files,
        };
    }

    close(): void {
        this.db.close();
    }
}

// ============================================================================
// Local Content Index Service
// ============================================================================

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
        this.fileExtensions = new Set(config.fileExtensions || ['.md', '.txt', '.json']);
    }

    /**
     * Start watching directories for file changes
     */
    startWatching(): void {
        if (this.watcher) {
            this.watcher.close();
        }

        const patterns = this.config.watchDirs.map(dir =>
            `${dir}/**/*{${Array.from(this.fileExtensions).join(',')}}`
        );

        this.watcher = watch(patterns, {
            ignored: /(^|[\/\\])\../, // Ignore dotfiles
            persistent: true,
            ignoreInitial: false,
        });

        this.watcher
            .on('add', (filePath) => this.indexFile(filePath))
            .on('change', (filePath) => this.indexFile(filePath))
            .on('unlink', (filePath) => this.store.deleteByFilePath(filePath));

        console.log(`[LocalContentRAG] Watching: ${this.config.watchDirs.join(', ')}`);
    }

    /**
     * Stop watching directories
     */
    stopWatching(): void {
        if (this.watcher) {
            this.watcher.close();
            this.watcher = undefined;
        }
    }

    /**
     * Index a single file
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
     * Search for relevant content
     */
    async search(query: string, topK: number = 5): Promise<SearchResult[]> {
        const queryEmbedding = await this.embedder.generateEmbedding(query);
        return this.store.search(queryEmbedding, topK);
    }

    /**
     * Get index statistics
     */
    getStats(): { totalChunks: number; totalFiles: number; watchDirs: string[] } {
        const dbStats = this.store.getStats();
        return {
            ...dbStats,
            watchDirs: this.config.watchDirs,
        };
    }

    /**
     * Close resources
     */
    close(): void {
        this.stopWatching();
        this.store.close();
    }
}

// ============================================================================
// MCP Tool Export
// ============================================================================

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
        throw new Error('LocalContentRAG not initialized');
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
