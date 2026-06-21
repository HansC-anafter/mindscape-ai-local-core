import * as fs from "fs/promises";
import * as path from "path";
import * as crypto from "crypto";

import type { ContentChunk } from "./local_content_rag_types.js";

export class ContentChunker {
    private chunkSize: number;
    private chunkOverlap: number;

    constructor(chunkSize = 500, chunkOverlap = 100) {
        this.chunkSize = chunkSize;
        this.chunkOverlap = chunkOverlap;
    }

    /**
     * Split content into chunks based on file type.
     */
    async chunkFile(filePath: string): Promise<ContentChunk[]> {
        const ext = path.extname(filePath).toLowerCase();
        const content = await fs.readFile(filePath, "utf-8");
        const stat = await fs.stat(filePath);

        switch (ext) {
            case ".md":
                return this.chunkMarkdown(filePath, content, stat.mtime.toISOString());
            case ".txt":
                return this.chunkPlainText(filePath, content, stat.mtime.toISOString());
            case ".json":
                return this.chunkJson(filePath, content, stat.mtime.toISOString());
            default:
                return this.chunkPlainText(filePath, content, stat.mtime.toISOString());
        }
    }

    private chunkMarkdown(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        const chunks: ContentChunk[] = [];
        const lines = content.split("\n");

        let currentSection = "";
        let currentChunk = "";
        let startLine = 1;
        let lineNum = 1;

        for (const line of lines) {
            if (line.startsWith("#")) {
                if (currentChunk.trim()) {
                    chunks.push(this.createChunk(
                        filePath, currentChunk, startLine, lineNum - 1,
                        "markdown", modifiedAt, currentSection
                    ));
                }
                currentSection = line.replace(/^#+\s*/, "");
                currentChunk = line + "\n";
                startLine = lineNum;
            } else {
                currentChunk += line + "\n";

                if (currentChunk.length > this.chunkSize) {
                    chunks.push(this.createChunk(
                        filePath, currentChunk, startLine, lineNum,
                        "markdown", modifiedAt, currentSection
                    ));
                    currentChunk = "";
                    startLine = lineNum + 1;
                }
            }
            lineNum++;
        }

        if (currentChunk.trim()) {
            chunks.push(this.createChunk(
                filePath, currentChunk, startLine, lineNum - 1,
                "markdown", modifiedAt, currentSection
            ));
        }

        return chunks;
    }

    private chunkPlainText(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        const chunks: ContentChunk[] = [];
        const lines = content.split("\n");

        let currentChunk = "";
        let startLine = 1;

        for (let i = 0; i < lines.length; i++) {
            currentChunk += lines[i] + "\n";

            if (currentChunk.length >= this.chunkSize) {
                chunks.push(this.createChunk(
                    filePath, currentChunk, startLine, i + 1,
                    "text", modifiedAt
                ));

                const overlapLines = Math.ceil(this.chunkOverlap / 50);
                startLine = Math.max(1, i + 1 - overlapLines);
                currentChunk = lines.slice(startLine - 1, i + 1).join("\n") + "\n";
            }
        }

        if (currentChunk.trim()) {
            chunks.push(this.createChunk(
                filePath, currentChunk, startLine, lines.length,
                "text", modifiedAt
            ));
        }

        return chunks;
    }

    private chunkJson(filePath: string, content: string, modifiedAt: string): ContentChunk[] {
        try {
            const parsed = JSON.parse(content);
            const readable = JSON.stringify(parsed, null, 2);
            return [this.createChunk(filePath, readable, 1, 1, "json", modifiedAt)];
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
        const id = crypto.createHash("sha256")
            .update(`${filePath}:${startLine}:${endLine}`)
            .digest("hex")
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
