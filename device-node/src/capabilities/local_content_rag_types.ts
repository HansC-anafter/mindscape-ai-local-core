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
    embeddingProvider: "ollama" | "openai";
    ollamaUrl?: string;
    ollamaModel?: string;
    openaiApiKey?: string;
    dbPath: string;
    chunkSize?: number;
    chunkOverlap?: number;
    fileExtensions?: string[];
}
