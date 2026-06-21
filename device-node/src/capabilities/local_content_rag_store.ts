import Database from "better-sqlite3";

import type { ContentChunk, SearchResult } from "./local_content_rag_types.js";

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
        this.db.prepare("DELETE FROM chunks WHERE file_path = ?").run(filePath);
    }

    async search(queryEmbedding: number[], topK: number = 5): Promise<SearchResult[]> {
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
